import asyncio
import time
from rcb_config import CONFIG, get_random_proxy, get_headers, get_proxy_ip
from notifier import send_telegram


async def event_watcher(session, token_pool, logger) -> dict:
    """
    Poll the event list until a live event is found.

    Flash-LIVE protection:
      LIVE_CONFIRM_COUNT in config controls how many consecutive LIVE polls
      are required before the event is declared truly live. Default is 2.
      - Set to 1 for instant trigger (risky: flash-live false positives).
      - Set to 2-3 to avoid triggering on a 2-3 second "coming soon → live → coming soon" blip.
      Each confirm poll is fired back-to-back with no sleep between them.
    """
    url = f"{CONFIG['BASE_URL']}/ticket/eventlist/O"
    confirm_needed = max(1, CONFIG.get("LIVE_CONFIRM_COUNT", 2))

    HEARTBEAT_INTERVAL = 6 * 3600  # 6 hours in seconds
    last_heartbeat = time.time()
    token_idx = 0
    live_streak = 0        # consecutive LIVE detections
    live_event = None      # candidate event to return

    proxy_url = get_random_proxy()
    proxy_use_count = 0

    while True:
        try:
            if proxy_use_count >= 5:
                proxy_url = get_random_proxy()
                proxy_use_count = 0
            
            proxy_use_count += 1

            # Rotate token for each request
            token = token_pool[token_idx % len(token_pool)]
            token_idx += 1
            headers = get_headers(token=token['token'])
            ip = await get_proxy_ip(session, proxy_url)
            logger.info(f"🌐 Event Watcher Poll IP: {ip}")
            async with session.get(url, headers=headers, proxy=proxy_url) as res:
                if res.status != 200:
                    logger.warning(f"⚠️ Event poll HTTP Error {res.status}")
                    live_streak = 0
                    await asyncio.sleep(10)
                    continue

                try:
                    data = await res.json(content_type=None)
                except Exception:
                    raw = await res.text()
                    logger.error(f"❌ Event poll: Received non-JSON response (starts with: {raw[:100].strip()}...)")
                    live_streak = 0
                    await asyncio.sleep(30)
                    continue

                results = data.get("result", [])
                if not isinstance(results, list):
                    logger.warning(f"⚠️ Event poll returned unexpected result format: {results}")
                    results = []

                found_live = None
                for event in results:
                    if event.get("event_Button_Text", "").upper() == "BUY TICKETS":
                        found_live = event
                        break

                if found_live:
                    live_streak += 1
                    live_event = found_live
                    if live_streak < confirm_needed:
                        logger.info(
                            f"🟡 Event looks LIVE ({live_streak}/{confirm_needed} confirms)... "
                            f"re-polling immediately to confirm."
                        )
                        # No sleep — confirm as fast as possible
                        continue
                    else:
                        # Confirmed live!
                        return live_event
                else:
                    if live_streak > 0:
                        logger.warning(
                            f"⚠️ Flash-LIVE: event was live for {live_streak} poll(s) then went back to "
                            f"coming-soon. Resetting streak — will wait for stable LIVE."
                        )
                    live_streak = 0
                    live_event = None

        except Exception as e:
            logger.warning(f"⚠️ Event poll error: {e}")
            await send_telegram(f"⚠️ Event poll error: {e}")
            live_streak = 0

        # 6-hour heartbeat
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            last_heartbeat = now
            await send_telegram("🕐 RCB Bot still polling... waiting for event to go LIVE.")
            logger.info("🕐 Sent 6-hr heartbeat (still waiting)")

        await asyncio.sleep(CONFIG["EVENT_CHECK_INTERVAL"])