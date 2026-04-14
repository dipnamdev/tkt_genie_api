import asyncio
import time
from rcb_config import CONFIG, get_random_proxy, get_headers, get_proxy_ip
from notifier import send_telegram


async def event_watcher(session, token_pool, logger) -> dict:
    """
    Poll the event list until a live event is found.
    Rotating tokens for each request as per user requirement.
    """
    url = f"{CONFIG['BASE_URL']}/ticket/eventlist/O"
    
    HEARTBEAT_INTERVAL = 6 * 3600  # 6 hours in seconds
    last_heartbeat = time.time()
    token_idx = 0

    while True:
        try:
            # Rotate token for each request
            token = token_pool[token_idx % len(token_pool)]
            token_idx += 1
            headers = get_headers(token=token['token'])

            proxy_url = get_random_proxy()
            ip = await get_proxy_ip(session, proxy_url)
            logger.info(f"🌐 Event Watcher Poll IP: {ip}")
            async with session.get(url, headers=headers, proxy=proxy_url) as res:
                if res.status != 200:
                    logger.warning(f"⚠️ Event poll HTTP Error {res.status}")
                    await asyncio.sleep(10)
                    continue

                try:
                    data = await res.json(content_type=None)
                except Exception:
                    raw = await res.text()
                    logger.error(f"❌ Event poll: Received non-JSON response (starts with: {raw[:100].strip()}...)")
                    await asyncio.sleep(30)
                    continue

                results = data.get("result", [])
                if not isinstance(results, list):
                    logger.warning(f"⚠️ Event poll returned unexpected result format: {results}")
                    results = []

                for event in results:
                    # User-customized check for 'BUY TICKETS' label
                    if event.get("event_Button_Text", "").upper() == "BUY TICKETS":
                        return event

        except Exception as e:
            logger.warning(f"⚠️ Event poll error: {e}")
            await send_telegram(f"⚠️ Event poll error: {e}")
            # Log periodically if the error persists to avoid flooding but keep visibility

        # 6-hour heartbeat
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            last_heartbeat = now
            await send_telegram("🕐 RCB Bot still polling... waiting for event to go LIVE.")
            logger.info("🕐 Sent 6-hr heartbeat (still waiting)")

        await asyncio.sleep(CONFIG["EVENT_CHECK_INTERVAL"])