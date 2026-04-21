import json
import os
import uuid

# ── DEFAULT CONFIGURATION ────────────────────────────────────────────────
# These are fallback values. The bot will prioritize 'config.json'.
DEFAULT_CONFIG = {
    # Telegram
    "TELEGRAM_TOKEN": "",
    "TELEGRAM_TOKEN_BOOK": "",
    "TELEGRAM_CHAT_IDS": [],
    "TELEGRAM_ADMIN_CHAT_IDS": [],

    # Token source
    "GITHUB_TOKEN_URL": "https://raw.githubusercontent.com/dipnamdev/tkt_genie_api/refs/heads/main/rcbTokens.json",

    # API
    "BASE_URL": "https://rcbscaleapi.ticketgenie.in",
    "REQUEST_TIMEOUT": 3,

    # Proxy (IPRoyal Residential)
    "USE_PROXY": False,
    "PROXY_USER": "",
    "PROXY_PASS_BASE": "",
    "PROXY_HOST": "geo.iproyal.com",
    "PROXY_PORT": "12321",

    # Datacenter / ISP proxies pool
    "DATACENTER_PROXIES": [],

    # Timing
    "EVENT_CHECK_INTERVAL": 2,
    "SEAT_CHECK_INTERVAL": 1,

    # Concurrency
    "MAX_WORKERS": 20,
    "MAX_TICKETS_PER_TOKEN": 2,

    # Flash-LIVE protection
    "LIVE_CONFIRM_COUNT": 2,

    # Stands to monitor
    "PREFERRED_STANDS": [],
}

def load_config():
    """Load config.json and merge with DEFAULT_CONFIG."""
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
    """Generate a rotating residential proxy URL (IPRoyal) for event watcher."""
    if not CONFIG.get("USE_PROXY"):
        return None
        
    user = CONFIG.get("PROXY_USER")
    pass_base = CONFIG.get("PROXY_PASS_BASE")
    host = CONFIG.get("PROXY_HOST")
    port = CONFIG.get("PROXY_PORT")

    if not all([user, pass_base, host, port]):
        return None

    session_id = uuid.uuid4().hex[:8]
    return f"http://{user}:{pass_base}_session-{session_id}@{host}:{port}"


def get_dc_proxy() -> str | None:
    """
    Pick a random datacenter/ISP proxy from DATACENTER_PROXIES list.
    Returns None (Local IP) if list is empty.
    """
    import random
    dc_proxies = CONFIG.get("DATACENTER_PROXIES", [])
    if dc_proxies:
        return random.choice(dc_proxies)
    return None  # Fallback to local IP

async def get_proxy_ip(session, proxy_url: str) -> str:
    """Fetch the actual IP assigned for a specific proxy URL."""
    if not proxy_url:
        return "LOCAL"
    try:
        async with session.get("http://ipv4.icanhazip.com", proxy=proxy_url, timeout=3) as res:
            if res.status == 200:
                ip = await res.text()
                return ip.strip()
            return f"Error {res.status}"
    except Exception as e:
        return f"Fetch Error: {e}"

def get_headers(token=None, is_post=False):
    """Returns headers with modern browser footprint."""
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
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