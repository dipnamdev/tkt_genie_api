import asyncio
import aiohttp
import logging
import os
from rcb_config import CONFIG
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

    # Get absolute path for log file (saved in same folder as script)
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
        await asyncio.sleep(3600)  # 60 minutes
        try:
            logger.info("🔄 Refreshing tokens from GitHub...")
            new_tokens = await load_tokens()
            if new_tokens:
                # Update the pool in-place so all references see the new data
                token_pool[:] = new_tokens
                logger.info(f"✅ Token pool refreshed! Total: {len(token_pool)}")
        except Exception as e:
            logger.error(f"⚠️ Token refresh failed: {e}")

async def main():
    logger = setup_logger()
    logger.info("🚀 Starting RCB Bot...")
    await send_telegram("🚀 Starting RCB Bot..");

    try:
        # ── Load tokens ───────────────────────────────────────────────────
        logger.info("🔑 Loading tokens from GitHub...")
        token_pool = await load_tokens()
        logger.info(f"✅ Loaded {len(token_pool)} tokens")

        # ── Initialize Queue ─────────────────────────────────────────────
        init_queue()
        logger.info("📦 Queue initialized")

        # ── Session with shared timeout ───────────────────────────────────
        timeout = aiohttp.ClientTimeout(total=CONFIG.get("REQUEST_TIMEOUT", 3))

        async with aiohttp.ClientSession(timeout=timeout) as session:
           
            # ── Wait for event to go live ─────────────────────────────────
            
            logger.info("👀 Waiting for event to go LIVE...")
            event = await event_watcher(session, token_pool, logger)
            logger.info(
                f"🔥 EVENT LIVE: {event.get('event_Name')} | "
                f"ID={event.get('event_Code')}"
            )
            await send_telegram( f"🔥 EVENT LIVE: {event.get('event_Name')}   https://shop.royalchallengers.com/ticket ")

            # ── Background tasks and keep references ──────────────────────
            tasks = []
            
            # ── Background cleanup task ───────────────────────────────────
            tasks.append(asyncio.create_task(cleanup_loop(logger)))

            # ── Periodic token refresher (60 mins) ────────────────────────
            tasks.append(asyncio.create_task(token_refresh_loop(token_pool, logger)))

            # ── Start one stand manager per preferred stand ───────────────
            stands = CONFIG.get("PREFERRED_STANDS", [])
            logger.info(f"🎯 Monitoring stands: {stands}")

            for stand_id in stands:
                tasks.append(asyncio.create_task(
                    stand_manager(session, stand_id, event, token_pool, logger)
                ))

            # ── Start worker pool ─────────────────────────────────────────
            worker_count = CONFIG.get("MAX_WORKERS", 20)
            logger.info(f"⚡ Starting {worker_count} workers...")

            for _ in range(worker_count):
                tasks.append(asyncio.create_task(
                    worker(session, token_pool, event, logger)
                ))

            # ── Wait for all tasks ────────────────────────────────────────
            logger.info("🔥 All systems active. Monitoring...")
            await asyncio.gather(*tasks)

    except Exception as e:
        logger.exception(f"❌ Fatal error in main: {e}")
        await send_telegram(f"❌ RCB Bot crashed: {e}")


# ================= ENTRY =================

if __name__ == "__main__":
    asyncio.run(main())
