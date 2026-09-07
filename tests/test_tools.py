import unittest
import asyncio
from services.text_cleaner import clean_spoken_text, split_stream_sentences
from services.tools.registry import TOOLS_SCHEMA, TOOL_DISPATCH_MAP, dispatch_tool

class TestTextCleaner(unittest.TestCase):
    def test_clean_spoken_text_markdown(self):
        raw = "Hello **world**! This is *italic* and `code`."
        cleaned = clean_spoken_text(raw)
        self.assertEqual(cleaned, "Hello world! This is italic and code.")

    def test_clean_spoken_text_xml_tags(self):
        raw = "<minimax:toolcall>fetch_weather</minimax:toolcall>Good morning!"
        cleaned = clean_spoken_text(raw)
        self.assertEqual(cleaned, "Good morning!")

    def test_clean_spoken_text_lists_and_headers(self):
        raw = "## Agenda\n- Buy groceries\n- Finish coding"
        cleaned = clean_spoken_text(raw)
        self.assertEqual(cleaned, "Agenda Buy groceries Finish coding")

    def test_split_stream_sentences(self):
        buffer = "Hello there. How are you doing? I am"
        ready, remainder = split_stream_sentences(buffer)
        self.assertEqual(ready, ["Hello there.", "How are you doing?"])
        self.assertEqual(remainder, "I am")

class TestToolRegistry(unittest.TestCase):
    def test_no_execute_sql_in_schema(self):
        tool_names = [t["function"]["name"] for t in TOOLS_SCHEMA]
        self.assertNotIn("execute_sql", tool_names)
        self.assertIn("fetch_weather", tool_names)
        self.assertIn("add_task", tool_names)
        self.assertIn("log_expense", tool_names)
        self.assertIn("start_timer", tool_names)

    def test_dispatch_unknown_tool(self):
        async def run_test():
            result = await dispatch_tool("nonexistent_hack_tool", {})
            self.assertIn("not recognized", result)
        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
