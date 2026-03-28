import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
load_dotenv(".env.local")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def test_search(search_query):
    print(f"\nSearching for: '{search_query}'")
    
    # Logic copied from brain.py
    normalized_query = search_query.lower()
    if "name" in normalized_query or "who am i" in normalized_query or "identity" in normalized_query:
        search_terms = ["name", "identity", "pref"]
    else:
        search_terms = [search_query]

    all_memories = []
    for term in search_terms:
        response = supabase.table("core_memory") \
            .select("*") \
            .ilike("memory_text", f"%{term}%") \
            .limit(5) \
            .execute()
        if response.data:
            all_memories.extend(response.data)
    
    seen_texts = set()
    unique_memories = []
    for m in all_memories:
        if m['memory_text'] not in seen_texts:
            unique_memories.append(m)
            seen_texts.add(m['memory_text'])
    
    if not unique_memories:
        print("No results found.")
        return
    
    for i, entry in enumerate(unique_memories[:5], 1):
        print(f"{i}. {entry['memory_text']} (ID: {entry['id']})")

async def main():
    await test_search("user name")
    await test_search("what is my name")
    await test_search("who am i")

if __name__ == "__main__":
    asyncio.run(main())
