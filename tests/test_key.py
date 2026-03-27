import asyncio
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv(".env.local")
api_key = os.getenv("ASSEMBLYAI_API_KEY")


async def test_key_http():
    print(f"Testing AssemblyAI API Key via HTTP: {api_key[:5]}...{api_key[-5:]}")
    headers = {"Authorization": api_key}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.assemblyai.com/v2/transcript", headers=headers) as response:
                if response.status == 200:
                    print("PASS: API key is valid for HTTP requests.")
                    return True

                text = await response.text()
                print(f"FAIL: API key test failed with status {response.status}: {text}")
                return False
    except Exception as e:
        print(f"FAIL: API key test failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_key_http())
