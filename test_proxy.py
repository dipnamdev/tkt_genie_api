import asyncio
import aiohttp
from rcb_config import get_random_proxy
from notifier import _send

# async def check_ip(session, index):
#     proxy = get_random_proxy()
#     hidden_proxy = proxy.split('@')[-1] if proxy else "None"
    
#     try:
#         async with session.get("http://ipv4.icanhazip.com", proxy=proxy, timeout=10) as res:
#             ip = await res.text()
#             print(f"[{index}] Proxy Target: {hidden_proxy} | Response IP: {ip.strip()}")
#             return ip.strip()
#     except Exception as e:
#         print(f"[{index}] Error with proxy {hidden_proxy}: {e}")
#         return None

# async def main():
#     print("Testing IPRoyal Proxy Rotation with Keep-Alive Session...")
#     async with aiohttp.ClientSession() as session:
#         # Run 5 requests concurrently using the same connection pool
#         tasks = [check_ip(session, i) for i in range(1, 6)]
#         results = await asyncio.gather(*tasks)
        
#         ips = [r for r in results if r]
#         unique_ips = set(ips)
        
#         print(f"\nTested 5 concurrent requests.")
#         print(f"Got {len(unique_ips)} unique IPs:")
#         for ip in unique_ips:
#             print(f" - {ip}")

async def main():
    msg = "This is test Message from RCB Bot to verify Telegram notifications are working correctly. When Tickets are booked successfully, you will receive a message like this with seat details and account info. If you see this, Telegram notifications are configured properly!"
    await _send(msg, book=True)

if __name__ == "__main__":
    asyncio.run(main())
