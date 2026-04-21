import aiohttp
import asyncio
import json
import os
from rcb_config import CONFIG


# ================= TOKEN LOADER =================

async def load_tokens(retries: int = 3, timeout: int = 10, logger=None) -> list:
    """
    Load tokens. Prioritize local tokens.json, fall back to GitHub.

    Expected format:
    [
        {
            "ac_name": "Name",
            "cookie": "<bearer_token>",
            "loggedin_by": "user_name"
        }
    ]
    """
    # ── Check local file first ───────────────────────────────────────
    # base_dir = os.path.dirname(os.path.abspath(__file__))
    # local_path = os.path.join(base_dir, "tokens.json")
    # if os.path.exists(local_path):
    #     try:
    #         with open(local_path, "r") as f:
    #             data = json.load(f)
    #             tokens = parse_token_data(data)
    #             if tokens:
    #                 print(f"✅ Loaded {len(tokens)} tokens from local tokens.json")
    #                 return tokens
    #     except Exception as e:
    #         print(f"⚠️ Warning: Could not read local tokens.json: {e}")

    # ── Fallback to GitHub ───────────────────────────────────────────
    url = CONFIG.get("GITHUB_TOKEN_URL")
    if not url:
        raise ValueError("❌ GITHUB_TOKEN_URL not set and local tokens.json missing")

    for attempt in range(1, retries + 1):
        try:
            timeout_cfg = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.get(url) as res:
                    if res.status != 200:
                        raise Exception(f"HTTP {res.status}")
                    data = await res.json(content_type=None)

            tokens = parse_token_data(data)
            if not tokens:
                raise Exception("No valid tokens found in JSON")

            if logger:
                logger.info(f"Loaded {len(tokens)} tokens from GitHub")
            else:
                print(f"Loaded {len(tokens)} tokens from GitHub")
            return tokens
 
        except Exception as e:
            if logger:
                logger.warning(f"Token load attempt {attempt} failed: {e}")
            else:
                print(f"Token load attempt {attempt} failed: {e}")
            
            if attempt == retries:
                raise Exception("Failed to load tokens after retries")
            await asyncio.sleep(2)


def parse_token_data(data: list) -> list:
    """Helper to parse token list into internal pool format."""
    tokens = []
    for idx, item in enumerate(data):
        try:
            token = item.get("cookie")
            name = item.get("ac_name", f"user_{idx}")
            loggedin_by = item.get("loggedin_by", name)
            mob_no = item.get("mob_no", "N/A")

            if not token:
                continue

            tokens.append({
                "name": name,
                "token": token,
                "loggedin_by": loggedin_by,
                "mob_no": mob_no,
                "used": 0,
                "last_used": 0.0,
            })
        except Exception:
            continue
    return tokens
