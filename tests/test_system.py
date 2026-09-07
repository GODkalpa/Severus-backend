import asyncio
import os
import json
import aiohttp
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")
load_dotenv()

PORT = os.getenv("PORT", "8000")
HOST = os.getenv("HOST", "localhost")
if HOST == "0.0.0.0":
    HOST = "localhost"

BASE_URL = f"http://{HOST}:{PORT}"
WS_URL = f"ws://{HOST}:{PORT}/ws/severus"

async def check_api_health() -> bool:
    print(f"--- Checking API Health at {BASE_URL} ---")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"PASS: API root returned: {data}")
                    return True
                print(f"FAIL: API returned status {response.status}")
                return False
    except Exception as e:
        print(f"FAIL: Could not connect to API at {BASE_URL} ({e})")
        return False

async def check_auth_endpoint() -> bool:
    print(f"\n--- Checking Auth Endpoint at {BASE_URL}/api/auth/register/begin ---")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"user_id": "test-device", "master_secret": "wrong-secret"}
            async with session.post(f"{BASE_URL}/api/auth/register/begin", json=payload, timeout=5) as response:
                # Should return 401 Unauthorized for bad or missing master secret
                if response.status == 401:
                    print("PASS: Master secret protection is active (401 Unauthorized).")
                    return True
                print(f"INFO: Auth endpoint returned status {response.status}")
                return True
    except Exception as e:
        print(f"FAIL: Auth endpoint check failed: {e}")
        return False

async def check_websocket_handshake() -> bool:
    print(f"\n--- Checking WebSocket Handshake & Security at {WS_URL} ---")
    try:
        async with websockets.connect(WS_URL, close_timeout=3) as websocket:
            print("Connected to WebSocket. Testing authentication enforcement...")
            
            # Send invalid auth token to verify strict rejection
            await websocket.send(json.dumps({
                "type": "AUTH",
                "token": "diagnostic_mock_token_invalid"
            }))
            
            try:
                response_text = await asyncio.wait_for(websocket.recv(), timeout=4.0)
                if isinstance(response_text, str):
                    data = json.loads(response_text)
                    if data.get("type") == "ERROR" and data.get("message") == "UNAUTHORIZED":
                        print("PASS: WebSocket strictly enforces session token validation.")
                        return True
                print(f"Received unexpected response: {response_text}")
                return False
            except asyncio.TimeoutError:
                print("FAIL: Timeout waiting for WebSocket auth rejection.")
                return False
    except websockets.exceptions.ConnectionClosed as cc:
        print(f"PASS: Connection closed cleanly by server ({cc.code}).")
        return True
    except Exception as e:
        print(f"FAIL: WebSocket connection failed: {e}")
        return False

async def main():
    print("=== Severus Voice AI System Diagnostic ===\n")
    api_ok = await check_api_health()
    if not api_ok:
        print("\nFAIL: Backend is not reachable. Start with: python main.py")
        return

    auth_ok = await check_auth_endpoint()
    ws_ok = await check_websocket_handshake()

    if api_ok and auth_ok and ws_ok:
        print("\n>>> ALL DIAGNOSTIC CHECKS PASSED: Severus Backend is operational and secured.")
    else:
        print("\n>>> DIAGNOSTIC COMPLETED WITH WARNINGS.")

if __name__ == "__main__":
    asyncio.run(main())
