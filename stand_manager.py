import asyncio
import aiohttp
import time
from rcb_config import CONFIG, get_headers, get_random_proxy, get_proxy_ip
import queue_manager

BASE_URL = CONFIG["BASE_URL"]

# ================= PRIORITY FUNCTION =================

def seat_priority(seat):
    """Lower = higher priority. Sort by row_Order then seat_No."""
    return (seat.get("row_Order", 999), seat.get("seat_No", 9999))


# ================= STAND MANAGER =================

async def stand_manager(session, stand_id, event, token_pool, logger):
    """
    Continuously polls the seatlist for a given stand.
    Rotates through token_pool for each request (fastest + avoids rate limits).
    Pushes available, non-blacklisted seats to seat_queue.
    """
    url = (
        f"{BASE_URL}/ticket/seatlist"
        f"/{event['event_Group_Code']}"
        f"/{event['event_Code']}"
        f"/{stand_id}"
    )

    logger.info(f"🎯 Stand Manager started for Stand {stand_id}")

    last_seen: dict = {}   # seat_id -> timestamp (cooldown guard)
    token_idx = 0          # round-robin index

    while True:
        try:
            # rotate token for each seatlist call
            token = token_pool[token_idx % len(token_pool)]
            token_idx += 1

            headers = get_headers(token=token['token'])

            proxy_url = get_random_proxy()
            ip = await get_proxy_ip(session, proxy_url)
            logger.info(f"🌐 Stand {stand_id} Poll IP: {ip}")
            timeout = aiohttp.ClientTimeout(total=CONFIG["REQUEST_TIMEOUT"])
            async with session.get(url, headers=headers, proxy=proxy_url, timeout=timeout) as res:
                if res.status != 200:
                    text = await res.text()
                    logger.warning(f"⚠️ Stand {stand_id} HTTP Error {res.status}: {text[:100]}")
                    await asyncio.sleep(2)
                    continue

                try:
                    data = await res.json(content_type=None)
                except Exception as je:
                    raw = await res.text()
                    logger.error(f"❌ Stand {stand_id}: JSON parse error: {je}. Raw: {raw[:200]}")
                    await asyncio.sleep(2)
                    continue

            seats = data.get("result", [])
            now = time.time()
            available = []

            for seat in seats:
                status = seat.get("status", "").strip().upper()

                if status != "R":
                    continue

                seat_id = seat["i_Id"]

                # skip blacklisted seats immediately
                if queue_manager.is_blacklisted(seat_id):
                    continue

                # skip already-tracked seats
                current = queue_manager.seat_state.get(seat_id)
                if current in ("queued", "trying", "success", "blacklisted"):
                    continue

                # cooldown: don't re-add same seat within 1 second
                if seat_id in last_seen and now - last_seen[seat_id] < 1.0:
                    continue

                last_seen[seat_id] = now
                available.append(seat)

            if available:
                available.sort(key=seat_priority)

                for seat in available:
                    if not queue_manager.seat_queue:
                        await asyncio.sleep(0.1)
                        continue
                        
                    seat_id = seat["i_Id"]
                    queue_manager.seat_state[seat_id] = "queued"
                    await queue_manager.seat_queue.put(seat)

                logger.info(f"🔥 Stand {stand_id}: queued {len(available)} seats")

        except Exception as e:
            logger.error(f"❌ Stand {stand_id} error: {e}")

        await asyncio.sleep(CONFIG["SEAT_CHECK_INTERVAL"])
