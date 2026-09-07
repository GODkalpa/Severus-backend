import asyncio
import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def setup_auth_tables():
    print("Setting up Biometric Auth tables...")
    
    sql = """
    -- 1. Create the auth_credentials table
    CREATE TABLE IF NOT EXISTS public.auth_credentials (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        credential_id TEXT UNIQUE NOT NULL,
        public_key TEXT NOT NULL,
        sign_count INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        last_used_at TIMESTAMPTZ DEFAULT NOW(),
        transports TEXT[] 
    );

    -- 2. Create the auth_sessions table
    CREATE TABLE IF NOT EXISTS public.auth_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_token TEXT UNIQUE NOT NULL,
        credential_id TEXT REFERENCES public.auth_credentials(credential_id),
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- 3. Enable RLS
    ALTER TABLE public.auth_credentials ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.auth_sessions ENABLE ROW LEVEL SECURITY;

    -- 4. Initial Policies for Service Role
    -- (The backend uses the service_role/master key, so it bypasses RLS by default, 
    -- but we ensure the public can't read/write directly)
    DROP POLICY IF EXISTS "Deny public access" ON public.auth_credentials;
    CREATE POLICY "Deny public access" ON public.auth_credentials FOR ALL TO public USING (false);
    
    DROP POLICY IF EXISTS "Deny public access" ON public.auth_sessions;
    CREATE POLICY "Deny public access" ON public.auth_sessions FOR ALL TO public USING (false);
    """
    
    try:
        # Using the same RPC 'exec_sql' found in brain.py
        result = supabase.rpc("exec_sql", {"query_text": sql}).execute()
        print(f"Success: {result.data}")
    except Exception as e:
        print(f"Error setting up tables: {e}")

if __name__ == "__main__":
    asyncio.run(setup_auth_tables())
