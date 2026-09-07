import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)

def get_supabase() -> Client | None:
    return supabase
