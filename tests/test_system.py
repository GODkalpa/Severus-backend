import asyncio
import os

import aiohttp
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")

# Configuration
PORT = os.getenv("PORT", "8000")
HOST = os.getenv("HOST", "localhost")
if HOST == "0.0.0.0":
    HOST = "localhost"
BASE_URL = f"http://{HOST}:{PORT}"
WS_URL = f"ws://{HOST}:{PORT}/ws/severus"


async def check_api_health():
    print(f"--- Checking API Health at {BASE_URL} ---")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Success: {data}")
                    return True

                print(f"Failed: API returned status {response.status}")
                return False
    except Exception as e:
        print(f"Error: Could not connect to API. Is the server running? ({e})")
        return False


async def check_websocket_connection():
    print(f"\n--- Checking WebSocket at {WS_URL} ---")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("Successfully connected to WebSocket!")

            # Send a short silent audio chunk to exercise receive_bytes().
            print("Sending test audio chunk...")
            await websocket.send(bytes([0] * 1024))
            print("Waiting for response (Brain -> TTS loop)...")

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                if isinstance(response, bytes):
                    print(f"Received audio response: {len(response)} bytes")
                    return True

                print("Received unexpected non-binary response.")
                return False
            except asyncio.TimeoutError:
                print("Timeout: No response from server. (Check AssemblyAI logs)")
                return False

    except Exception as e:
        print(f"Error: WebSocket connection failed. ({e})")
        return False


async def main():
    print("=== Severus Voice AI System Diagnostic ===\n")

    api_ok = await check_api_health()

    if api_ok:
        ws_ok = await check_websocket_connection()
        if ws_ok:
            print("\nPASS: System seems to be working correctly.")
        else:
            print("\nFAIL: WebSocket flow failed.")
    else:
        print("\nFAIL: API is unreachable. Start the server with 'python main.py' first.")


if __name__ == "__main__":
    asyncio.run(main())
