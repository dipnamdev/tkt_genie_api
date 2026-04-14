import aiohttp
from rcb_config import CONFIG

# ================= SHARED HEADERS TEMPLATE =================

BASE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://shop.royalchallengers.com",
    "referer": "https://shop.royalchallengers.com/",
    "user-agent": "Mozilla/5.0",
}

# ================= INTERNAL SEND =================

async def _send(msg: str, book: bool = False):
    if book:
         token = CONFIG.get("TELEGRAM_TOKEN_BOOK", "")
         chat_ids = CONFIG.get("TELEGRAM_CHAT_IDS", [])

    else:
        token = CONFIG.get("TELEGRAM_TOKEN", "")
        chat_ids = CONFIG.get("TELEGRAM_ADMIN_CHAT_IDS", [])

    if not token or not chat_ids or token == "...":
        return  # Telegram not configured

    async with aiohttp.ClientSession() as session:
        for chat_id in chat_ids:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
            }
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        print(f"Telegram API error: {response.status} - {await response.text()}")
            except Exception as e:
                print(f"Telegram send error: {e}")  # Added logging for debugging


# ================= PUBLIC API =================

async def send_success(seat_nos: str, token: dict):
    """
    ✅ Booking SUCCESS — visually distinct (green, bold, celebratory)
    """
    msg = (
        "✅✅✅ <b>SEAT BOOKED SUCCESSFULLY!</b> ✅✅✅\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎟️ <b>Seat(s):</b> <code>{seat_nos}</code>\n"
        f"👤 <b>Account:</b> {token.get('name', 'N/A')}\n"
        f"📱 <b>Mobile:</b> <code>{token.get('mob_no', 'N/A')}</code>\n"
        f"🔑 <b>Logged in by:</b> {token.get('loggedin_by', 'N/A')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏏 RCB Bot — Booking Confirmed!"
        "⏰⏰ Only 5 minutes to complete payment! ⏰⏰"
    )
    await _send(msg, book=True)


async def send_failure(seat_nos: str, token: dict, reason: str):
    """
    ❌ Booking FAILURE — visually distinct (red, warning)
    """
    msg = (
        "⛔ <b>BOOKING FAILED</b> ⛔\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎟️ <b>Seat(s):</b> <code>{seat_nos}</code>\n"
        f"⚠️ <b>Reason:</b> {reason}\n"
        f"👤 <b>Account:</b> {token.get('name', 'N/A')}\n"
        f"📱 <b>Mobile:</b> <code>{token.get('mob_no', 'N/A')}</code>\n"
        f"🔑 <b>Logged in by:</b> {token.get('loggedin_by', 'N/A')}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await _send(msg)


async def send_telegram(msg: str):
    """Generic crash/system alert."""
    await _send(f"🤖 <b>RCB Bot:</b> {msg}")