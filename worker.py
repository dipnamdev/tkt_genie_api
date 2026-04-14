import asyncio
import random
import time
from rcb_config import CONFIG, get_headers, get_random_proxy, get_proxy_ip
import queue_manager
from notifier import send_success, send_failure

BOOK_API = f"{CONFIG['BASE_URL']}/checkout/ticketaddtocart"

# Errors that mean the seat is permanently gone — blacklist immediately
_HARD_FAIL_KEYWORDS = ("SEAT NOT AVAILABLE", "SOLD OUT", "ALREADY BOOKED", "INVALID SEAT", "STAND LIMIT EXCEEDED")

# ================= TOKEN PICKER =================

def get_token(token_pool: list) -> dict | None:
    """Pick a least-recently-used token that still has quota."""
    valid = [t for t in token_pool if t["used"] < CONFIG["MAX_TICKETS_PER_TOKEN"]]

    if not valid:
        return None

    # prefer tokens used least recently (cooldown-aware)
    valid.sort(key=lambda x: x.get("last_used", 0.0))
    return valid[0]   # fastest: always pick the coldest token


def group_by_stand(seats: list) -> dict[int, list]:
    """Partition a flat seat list into {stand_code: [seats]} buckets."""
    buckets = {}
    for s in seats:
        sc = s.get("stand_Code")
        if sc is not None:
            buckets.setdefault(sc, []).append(s)
    return buckets


def group_adjacent_seats(seats: list, max_group: int = 4) -> list[list]:
    """
    Group seats where i_Id values are consecutive.
    Confirmed by user: i_Id and serial_No are the best way to determine adjacency.
    """
    if not seats:
        return []

    # sort by i_Id for consecutiveness check
    seats = sorted(seats, key=lambda s: s["i_Id"])

    groups = []
    current = [seats[0]]

    for i in range(1, len(seats)):
        prev = seats[i - 1]
        curr = seats[i]

        is_consecutive = curr["i_Id"] == prev["i_Id"] + 1
        fits           = len(current) < max_group

        if is_consecutive and fits:
            current.append(curr)
        else:
            groups.append(current)
            current = [curr]

    groups.append(current)
    return groups


# ================= PAYLOAD BUILDER =================

def build_payload(group: list, event: dict) -> dict:
    # Confirmed working format: "U-11" or "T-21,T-20" (row-seat_No)
    seat_nos = ",".join(f"{s['row']}-{s['seat_No']}" for s in group)
    # Confirmed format: "1430,1429" (no space)
    seat_ids = ",".join(str(s["i_Id"]) for s in group)

    return {
        "eventGroupId": event["event_Group_Code"],
        "eventId":      event["event_Code"],
        "standId":      group[0]["stand_Code"],
        "qty":          len(group),
        "seatNos":      seat_nos,
        "seatIds":      seat_ids,
    }


# ================= SINGLE BOOKING COROUTINE =================

async def _book_group(session, group: list, event: dict, token: dict, logger):
    """Fire one booking request for a group of adjacent seats."""
    payload = build_payload(group, event)
    seat_nos = payload["seatNos"]

    headers = get_headers(token=token['token'], is_post=True)

    # mark all as 'trying'
    for s in group:
        queue_manager.seat_state[s["i_Id"]] = "trying"

    proxy_url = get_random_proxy()
    ip = await get_proxy_ip(session, proxy_url)
    logger.info(f"🌐 Worker IP for checkout: {ip}")
    try:
        async with session.post(BOOK_API, json=payload, headers=headers, proxy=proxy_url) as res:
            data = await res.json(content_type=None)

        msg = data.get("message", "")

        if data.get("status") == "Success":
            # One successful cart add = this token/cookie is DONE for the run
            token["used"] = CONFIG["MAX_TICKETS_PER_TOKEN"]  # exhaust immediately
            token["last_used"] = time.time()

            for s in group:
                queue_manager.seat_state[s["i_Id"]] = "success"

            logger.info(f"✅ BOOKED {seat_nos} via {token['name']}")
            await send_success(seat_nos, token)

        else:
            msg_upper = msg.upper()

            # decide fate of each seat
            for s in group:
                sid = s["i_Id"]
                if any(kw in msg_upper for kw in _HARD_FAIL_KEYWORDS):
                    queue_manager.blacklist_seat(sid)
                    logger.warning(f"🚫 Blacklisted seat {sid} | reason: {msg}")
                elif "LIMIT" in msg_upper:
                    # Token hit a limit — re-queue each seat individually so a
                    # fresh token can try them one at a time
                    queue_manager.seat_state[sid] = "queued"
                    await queue_manager.seat_queue.put(s)
                    logger.info(f"🔄 Re-queued seat {sid} for solo retry")
                else:
                    queue_manager.blacklist_seat(sid)   # unknown failure → safe to blacklist
                    logger.warning(f"🚫 Blacklisted seat {sid} | unknown: {msg}")

            logger.warning(f"❌ FAIL {seat_nos} | {msg}")
            # await send_failure(seat_nos, token, msg)

    except Exception as e:
        logger.error(f"❌ Request error for {seat_nos}: {e}")
        for s in group:
            queue_manager.seat_state[s["i_Id"]] = "retry"


# ================= WORKER =================

async def worker(session, token_pool: list, event: dict, logger):
    """
    Pulls seats from the queue, groups adjacent ones, and fires
    all booking requests concurrently via asyncio.gather for max speed.
    """
    max_batch = CONFIG["MAX_TICKETS_PER_TOKEN"]

    while True:
        try:
            if not queue_manager.seat_queue:
                await asyncio.sleep(0.1)
                continue
                
            seat = await queue_manager.seat_queue.get()

            if not seat:
                continue

            seat_id = seat["i_Id"]

            # guard: might have been blacklisted while waiting in queue
            if queue_manager.is_blacklisted(seat_id):
                continue
                
            if queue_manager.seat_state.get(seat_id) not in ("queued", "new"):
                continue

            # drain more seats from queue (non-blocking) to form a batch
            batch = [seat]
            try:
                while len(batch) < max_batch * 4:   # grab up to 4x capacity for grouping
                    extra = queue_manager.seat_queue.get_nowait()
                    if extra and not queue_manager.is_blacklisted(extra["i_Id"]):
                        if queue_manager.seat_state.get(extra["i_Id"]) in ("queued", "new"):
                            batch.append(extra)
            except asyncio.QueueEmpty:
                pass

            # group by stand first, then by consecutive i_Id within each stand
            stand_buckets = group_by_stand(batch)
            groups = []
            for stand_seats in stand_buckets.values():
                groups.extend(group_adjacent_seats(stand_seats, max_batch))

            # build one coroutine per group, each with its own token
            coros = []
            for group in groups:
                token = get_token(token_pool)
                if not token:
                    logger.warning("⚠️ All tokens exhausted")
                    # put seats back to retry later
                    for s in group:
                        queue_manager.seat_state[s["i_Id"]] = "queued"
                        await queue_manager.seat_queue.put(s)
                    await asyncio.sleep(0.5)
                    continue

                coros.append(_book_group(session, group, event, token, logger))

            if coros:
                # fire ALL group bookings simultaneously — maximum speed
                await asyncio.gather(*coros)

            await asyncio.sleep(0.01)   # tiny yield to event loop

        except Exception as e:
            logger.error(f"❌ Worker crash: {e}")
            await asyncio.sleep(0.5)
