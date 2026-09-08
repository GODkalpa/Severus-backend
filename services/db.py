import os
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv

# Load from both current working directory and backend root directory
backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(backend_dir / ".env.local", override=True)
load_dotenv(backend_dir / ".env", override=True)
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
