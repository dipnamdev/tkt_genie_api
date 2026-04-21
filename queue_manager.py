import asyncio
import time

# ================= GLOBAL QUEUE =================

seat_queue: asyncio.Queue | None = None

def init_queue():
    """Lazy initialization of the asyncio Queue to avoid issues with event loops at import time."""
    global seat_queue
    if seat_queue is None:
        seat_queue = asyncio.Queue(maxsize=10000)
    return seat_queue

# ================= SEAT STATE =================
# Lifecycle: new -> queued -> trying -> success / failed / retry

seat_state: dict = {}

# ================= GLOBAL BLACKLIST =================
# Seats added here are NEVER re-queued or re-attempted (global, permanent for this run)

blacklisted_seats: set = set()


def blacklist_seat(seat_id: int):
    """Permanently blacklist a seat for this run."""
    blacklisted_seats.add(seat_id)
    seat_state[seat_id] = "blacklisted"


def is_blacklisted(seat_id: int) -> bool:
    return seat_id in blacklisted_seats


# ================= RETRY TRACKING =================

retry_tracker: dict = {}
RETRY_DELAY = 1.5   # seconds between retries
MAX_RETRIES = 3


def can_retry(seat_id: int) -> bool:
    """Check if a seat can be retried (cooldown + count)."""
    now = time.time()
    info = retry_tracker.get(seat_id, {"count": 0, "last_try": 0})

    if info["count"] >= MAX_RETRIES:
        return False

    if now - info["last_try"] < RETRY_DELAY:
        return False

    return True


def mark_retry(seat_id: int):
    """Update retry metadata."""
    now = time.time()
    if seat_id not in retry_tracker:
        retry_tracker[seat_id] = {"count": 1, "last_try": now}
    else:
        retry_tracker[seat_id]["count"] += 1
        retry_tracker[seat_id]["last_try"] = now


def reset_seat(seat_id: int):
    """Reset seat for fresh attempt."""
    if seat_id in seat_state:
        seat_state[seat_id] = "new"


# ================= CLEANUP LOOP =================

async def cleanup_loop(logger=None):
    """Periodically cleans old retry/seat data to avoid memory bloat."""
    while True:
        try:
            now = time.time()

            to_delete = [
                sid for sid, info in retry_tracker.items()
                if now - info["last_try"] > 30
            ]
            for sid in to_delete:
                retry_tracker.pop(sid, None)

            if logger:
                logger.info(
                    f"🧹 Cleanup | retry_tracker={len(retry_tracker)} "
                    f"blacklisted={len(blacklisted_seats)}"
                )

        except Exception as e:
            if logger:
                logger.error(f"❌ Cleanup error: {e}")

        await asyncio.sleep(10)
