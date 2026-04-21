import asyncio
import aiohttp
import time

async def test_isp_proxy():
    proxy = "http://dipesh3rde:qWxT4Q2CQP@202.91.69.43:49155"
    url = "https://shop.royalchallengers.com/"
    
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    }
    
    print(f"Testing proxy: {proxy}")
    
    start_time = time.time()
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy, headers=headers) as res:
                end_time = time.time()
                print(f"Status Code: {res.status}")
                print(f"Response Time: {end_time - start_time:.4f} seconds")
                # Just read a little bit to confirm success
                _ = await res.read()
                print("✅ Successfully connected via ISP proxy!")
    except Exception as e:
        end_time = time.time()
        print(f"❌ Proxy test failed: {e}")
        print(f"Time elapsed before failure: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(test_isp_proxy())
