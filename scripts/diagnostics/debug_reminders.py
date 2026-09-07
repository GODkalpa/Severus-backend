
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from pprint import pprint

load_dotenv(".env.local", override=True)
load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_reminders():
    print("--- CURRENT REMINDERS ---")
    response = supabase.table("reminders").select("*").execute()
    pprint(response.data)

if __name__ == "__main__":
    check_reminders()
