import asyncio
import aiohttp
import logging
import os
from rcb_config import CONFIG, get_random_proxy, get_headers
from token_loader import load_tokens
from event_watcher import event_watcher
from stand_manager import stand_manager
from worker import worker
from queue_manager import cleanup_loop, init_queue
from notifier import send_telegram


# ================= LOGGING SETUP =================

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("rcb_bot")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "rcb_bot.log")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# ================= TOKEN REFRESHER =================

async def token_refresh_loop(token_pool: list, logger: logging.Logger):
    """Refetch tokens from GitHub every 60 minutes."""
    while True:
        await asyncio.sleep(3600)
        try:
            logger.info("🔄 Refreshing tokens from GitHub...")
            new_tokens = await load_tokens()
            if new_tokens:
                token_pool[:] = new_tokens
                logger.info(f"✅ Token pool refreshed! Total: {len(token_pool)}")
        except Exception as e:
            logger.error(f"⚠️ Token refresh failed: {e}")


# ================= SALE STATUS MONITOR =================

async def sale_status_monitor(session, token_pool: list, event: dict, logger: logging.Logger):
    """
    Monitors the event list while the bot is running after going LIVE.

    Handles two scenarios:
      1. Sale temporarily closes (e.g. 16:10 live → 16:15 closed → 16:30 reopen)
         - Logs a WARNING when the event drops to coming-soon
         - Logs INFO when it comes back live
         - NO restart needed: stand managers and workers self-recover automatically
           (queue just drains while closed, refills when reopened)

      2. Flash-LIVE during pre-sale (already handled by LIVE_CONFIRM_COUNT in event_watcher)

    This monitor is purely informational — it does NOT restart or cancel anything.
    It just tells you via Telegram and logs whether the sale is open or closed
    so you know NOT to manually restart the bot.
    """
    url = f"{CONFIG['BASE_URL']}/ticket/eventlist/O"
    token_idx = 0
    sale_open = True   # we enter this function only after confirmed LIVE
    CHECK_INTERVAL = CONFIG.get("EVENT_CHECK_INTERVAL", 2)

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)

            token = token_pool[token_idx % len(token_pool)]
            token_idx += 1
            headers = get_headers(token=token['token'])
            proxy_url = get_random_proxy()

            async with session.get(url, headers=headers, proxy=proxy_url,
                                   timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    continue
                data = await res.json(content_type=None)
                results = data.get("result", [])
                if not isinstance(results, list):
                    continue

                currently_live = any(
                    e.get("event_Button_Text", "").upper() == "BUY TICKETS"
                    for e in results
                )

                if sale_open and not currently_live:
                    # Sale just closed
                    sale_open = False
                    msg = (
                        "⏸️ Sale went OFFLINE (coming-soon). "
                        "Workers are idle — DO NOT restart the bot. "
                        "It will self-recover when sale reopens."
                    )
                    logger.warning(msg)
                    await send_telegram(f"⚠️ {msg}")

                elif not sale_open and currently_live:
                    # Sale reopened — bot recovers automatically
                    sale_open = True
                    msg = "✅ Sale is LIVE again! Bot auto-recovered — no restart needed."
                    logger.info(msg)
                    await send_telegram(f"🔥 {msg}")

        except Exception:
            pass   # monitor is non-critical, never let it crash other tasks


# ================= MAIN =================

async def main():
    logger = setup_logger()
    logger.info("🚀 Starting RCB Bot...")
    await send_telegram("🚀 Starting RCB Bot..")

    try:
        # ── Load tokens ───────────────────────────────────────────────────
        logger.info("🔑 Loading tokens from GitHub...")
        token_pool = await load_tokens()
        logger.info(f"✅ Loaded {len(token_pool)} tokens")

        # ── Initialize Queue ─────────────────────────────────────────────
        init_queue()
        logger.info("📦 Queue initialized")

        # ── Shared session ────────────────────────────────────────────────
        timeout = aiohttp.ClientTimeout(total=CONFIG.get("REQUEST_TIMEOUT", 3))

        async with aiohttp.ClientSession(timeout=timeout) as session:

            # ── Wait for event to go live (with flash-LIVE protection) ────
            logger.info("👀 Waiting for event to go LIVE...")
            event = await event_watcher(session, token_pool, logger)
            logger.info(
                f"🔥 EVENT LIVE: {event.get('event_Name')} | "
                f"ID={event.get('event_Code')}"
            )
            await send_telegram(
                f"🔥 EVENT LIVE: {event.get('event_Name')} "
                f"  https://shop.royalchallengers.com/ticket"
            )

            tasks = []

            # ── Background cleanup ────────────────────────────────────────
            tasks.append(asyncio.create_task(cleanup_loop(logger)))

            # ── Periodic token refresh (60 mins) ─────────────────────────
            tasks.append(asyncio.create_task(token_refresh_loop(token_pool, logger)))

            # ── Sale status monitor (close/reopen detection) ──────────────
            tasks.append(asyncio.create_task(
                sale_status_monitor(session, token_pool, event, logger)
            ))

            # ── Stand managers — start immediately, no pre-warm delay ─────
            stands = CONFIG.get("PREFERRED_STANDS", [])
            logger.info(f"🎯 Monitoring stands: {stands}")
            for stand_id in stands:
                tasks.append(asyncio.create_task(
                    stand_manager(session, stand_id, event, token_pool, logger)
                ))

            # ── Worker pool ───────────────────────────────────────────────
            worker_count = CONFIG.get("MAX_WORKERS", 20)
            logger.info(f"⚡ Starting {worker_count} workers...")
            for _ in range(worker_count):
                tasks.append(asyncio.create_task(
                    worker(session, token_pool, event, logger)
                ))

            logger.info("🔥 All systems active. Monitoring...")
            await asyncio.gather(*tasks)

    except Exception as e:
        logger.exception(f"❌ Fatal error in main: {e}")
        await send_telegram(f"❌ RCB Bot crashed: {e}")


# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(main())
