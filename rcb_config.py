import json
import os
import uuid

# Default values
DEFAULT_CONFIG = {
    # ── Telegram ──────────────────────────────────────────────────────────
    "TELEGRAM_TOKEN": "8422586220:AAGttjuWMoVUEPb-0vk2eX62gApCHCgumgI",
    "TELEGRAM_TOKEN_BOOK" : "8740379486:AAFzOTOhkL6v37OizS6ovCBogRUD2r0TwCI",
    "TELEGRAM_CHAT_IDS": [
    5672170730,
       6113458609,
       7717635724,
       1275297473,
       1084691194,
       1316879218,
       662897702,
       6334424658 ],
    "TELEGRAM_ADMIN_CHAT_IDS": [5672170730, 6113458609],  # for critical alerts only

    # ── Token source ──────────────────────────────────────────────────────
    "GITHUB_TOKEN_URL": "https://raw.githubusercontent.com/dipnamdev/tkt_genie_api/refs/heads/main/rcbToken.json",

    # ── API ───────────────────────────────────────────────────────────────
    "BASE_URL": "https://rcbscaleapi.ticketgenie.in",
    "REQUEST_TIMEOUT": 3,

    # ── Proxy (IPRoyal) ───────────────────────────────────────────────────
    "USE_PROXY": True,
    "PROXY_USER": "f5n2sGkXnhUyhPgT",
    "PROXY_PASS_BASE": "E3JIulqJDeUxUCXo_country-in",
    "PROXY_HOST": "geo.iproyal.com",
    "PROXY_PORT": "12321",

    # ── Timing ────────────────────────────────────────────────────────────
    "EVENT_CHECK_INTERVAL": 2,
    "SEAT_CHECK_INTERVAL": 1,

    # ── Concurrency ───────────────────────────────────────────────────────
    "MAX_WORKERS": 20,
    "MAX_TICKETS_PER_TOKEN": 2,

    # ── Stands to monitor ─────────────────────────────────────────────────
    "PREFERRED_STANDS": [9, 11, 12, 13, 14,8,5, 4],
}

def load_config():
    # Get the directory where this script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.json")
    
    config = DEFAULT_CONFIG.copy()

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"⚠️ Warning: Could not load config.json: {e}")

    return config

CONFIG = load_config()

def get_random_proxy() -> str | None:
    """Generate a rotating proxy URL for IPRoyal with a random session ID."""
    if not CONFIG.get("USE_PROXY"):
        return None
    session_id = uuid.uuid4().hex[:8]  # short random session ID
    user = CONFIG.get("PROXY_USER")
    pass_base = CONFIG.get("PROXY_PASS_BASE")
    host = CONFIG.get("PROXY_HOST")
    port = CONFIG.get("PROXY_PORT")

    # Important format: password_session-<ID>
    return f"http://{user}:{pass_base}_session-{session_id}@{host}:{port}"

async def get_proxy_ip(session, proxy_url: str) -> str:
    """Fetch the actual IP assigned by IPRoyal for this specific proxy URL."""
    if not proxy_url:
        return "LOCAL"
    try:
        # Hit a fast IP resolving service
        async with session.get("http://ipv4.icanhazip.com", proxy=proxy_url, timeout=3) as res:
            if res.status == 200:
                ip = await res.text()
                return ip.strip()
            return f"Error {res.status}"
    except Exception as e:
        return f"Fetch Error: {e}"

def get_headers(token=None, is_post=False):
    """
    Returns a dictionary of headers matching the user-provided browser footprint.
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"Bearer {token}" if token else None,
        "origin": "https://shop.royalchallengers.com",
        "priority": "u=1, i",
        "referer": "https://shop.royalchallengers.com/",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    }

    if token:
        headers["authorization"] = f"Bearer {token}"

    if is_post:
        headers["content-type"] = "application/json"

    return headers

    # 5672170730,
    #    6113458609,
    #    7717635724,
    #    1275297473,
    #    1084691194,
    #    1316879218,
    #    662897702,
    #    6334424658,
    #    840865734,
    #    6740772318,
    #    867565941