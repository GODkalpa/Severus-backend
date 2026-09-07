-- ==========================================================
-- Severus Personal Assistant - Consolidated Database Schema
-- Run this SQL in your Supabase Dashboard: SQL Editor -> New query -> Run
-- ==========================================================

-- 1. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==========================================================
-- 2. CORE ASSISTANT DATA TABLES
-- ==========================================================

-- Action Items / Todo Queue
CREATE TABLE IF NOT EXISTS public.action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task TEXT NOT NULL,
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    due_date TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_items_status ON public.action_items(status);
CREATE INDEX IF NOT EXISTS idx_action_items_created_at ON public.action_items(created_at DESC);

-- Biometrics & Health Telemetry
CREATE TABLE IF NOT EXISTS public.biometrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_type TEXT NOT NULL,
    value NUMERIC NOT NULL,
    unit TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    logged_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_biometrics_type_date ON public.biometrics(metric_type, logged_at DESC);

-- Financial Ledger / Expense Tracking
CREATE TABLE IF NOT EXISTS public.financial_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    amount NUMERIC NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    logged_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_financial_ledger_date ON public.financial_ledger(logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_financial_ledger_category ON public.financial_ledger(category);

-- Core Memory Vault
CREATE TABLE IF NOT EXISTS public.core_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_text TEXT NOT NULL,
    tags TEXT DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_core_memory_tags ON public.core_memory(tags);

-- Reminders & Timers (24/7 autonomous monitoring)
CREATE TABLE IF NOT EXISTS public.reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reminder_text TEXT NOT NULL,
    interval_hours NUMERIC DEFAULT 2.0,
    due_at TIMESTAMPTZ,
    is_one_off BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    last_notified_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminders_active ON public.reminders(is_active, due_at);

-- WebPush Subscriptions
CREATE TABLE IF NOT EXISTS public.push_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT UNIQUE NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- 3. BIOMETRIC WEBAUTHN & SESSION TABLES
-- ==========================================================

-- WebAuthn Passkeys / Credentials
CREATE TABLE IF NOT EXISTS public.auth_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    credential_id TEXT UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    sign_count INTEGER DEFAULT 0,
    transports TEXT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_credentials_cred_id ON public.auth_credentials(credential_id);

-- Biometric Authenticated Sessions
CREATE TABLE IF NOT EXISTS public.auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_token TEXT UNIQUE NOT NULL,
    credential_id TEXT REFERENCES public.auth_credentials(credential_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON public.auth_sessions(session_token);

-- ==========================================================
-- 4. ROW LEVEL SECURITY (RLS) & ACCESS POLICIES
-- ==========================================================

-- Enable RLS on all tables
ALTER TABLE public.action_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.biometrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.core_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_sessions ENABLE ROW LEVEL SECURITY;

-- Note: The Severus backend connects via the Supabase service_role key,
-- which automatically bypasses RLS.
-- The following policies secure direct client-side access:

DO $$ 
DECLARE
    tbl text;
BEGIN
    FOR tbl IN 
        SELECT unnest(ARRAY['action_items', 'biometrics', 'financial_ledger', 'core_memory', 'reminders', 'push_subscriptions'])
    LOOP
        EXECUTE format('
            DROP POLICY IF EXISTS "Allow authenticated full access" ON public.%I;
            CREATE POLICY "Allow authenticated full access" ON public.%I 
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
        ', tbl, tbl);
    END LOOP;
END $$;

-- Lock down sensitive auth tables from direct public/authenticated queries
DROP POLICY IF EXISTS "Deny public access" ON public.auth_credentials;
CREATE POLICY "Deny public access" ON public.auth_credentials FOR ALL TO public USING (false);

DROP POLICY IF EXISTS "Deny public access" ON public.auth_sessions;
CREATE POLICY "Deny public access" ON public.auth_sessions FOR ALL TO public USING (false);

-- ==========================================================
-- 5. SEED INITIAL DATA
-- ==========================================================

-- Seed default recurring hydration reminder
INSERT INTO public.reminders (reminder_text, interval_hours, last_notified_at, is_one_off, is_active)
VALUES ('Drink water // REVELIO_VITALS', 2.0, now(), false, true)
ON CONFLICT DO NOTHING;
