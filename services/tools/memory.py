from services.db import supabase

async def store_core_memory(memory_text: str, tags: str = "general") -> str:
    """
    Stores a piece of personal information into the core_memory table.
    """
    if not supabase:
        return "Core memory vault is not initialized."

    try:
        data = {
            "memory_text": memory_text.strip(),
            "tags": tags.strip() if tags else "general"
        }
        supabase.table("core_memory").insert(data).execute()
        return "The information has been stored in your core memory vault."
    except Exception as e:
        print(f"Error storing core memory: {e}")
        return f"Error vaulting memory: {str(e)}"


async def search_core_memory(search_query: str) -> str:
    """
    Searches core memory table for relevant information using flexible keyword matching.
    """
    if not supabase:
        return "Core memory vault is offline."

    try:
        normalized_query = search_query.strip().lower()
        if any(w in normalized_query for w in ["name", "who am i", "identity", "pref"]):
            search_terms = ["name", "identity", "pref", normalized_query]
        else:
            search_terms = [normalized_query]

        all_memories = []
        for term in search_terms:
            if not term:
                continue
            response = (
                supabase.table("core_memory")
                .select("*")
                .ilike("memory_text", f"%{term}%")
                .limit(5)
                .execute()
            )
            if response.data:
                all_memories.extend(response.data)

        # De-duplicate
        seen_texts = set()
        unique_memories = []
        for m in all_memories:
            text = m.get("memory_text", "")
            if text and text not in seen_texts:
                unique_memories.append(m)
                seen_texts.add(text)

        if not unique_memories:
            return "No relevant records found in the vault."

        lines = ["Core memory records:"]
        for i, entry in enumerate(unique_memories[:5], 1):
            lines.append(f"{i}. {entry['memory_text']}")

        return "\n".join(lines)
    except Exception as e:
        print(f"Error searching core memory: {e}")
        return f"Trouble retrieving records from vault: {str(e)}"
