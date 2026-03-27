import asyncio
import os
from dotenv import load_dotenv

# Add the parent directory to sys.path to import services
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.brain import store_core_memory, search_core_memory

async def test_memory():
    print("--- Testing Core Memory Tools ---")
    
    # Test storing a memory
    print("\n1. Testing store_core_memory...")
    store_result = await store_core_memory(
        "The user's favorite coffee is a flat white with no sugar.",
        "preference, coffee, breakfast"
    )
    print(f"Result: {store_result}")
    
    # Test searching for the memory
    print("\n2. Testing search_core_memory...")
    search_result = await search_core_memory("coffee")
    print(f"Result: {search_result}")

if __name__ == "__main__":
    asyncio.run(test_memory())
