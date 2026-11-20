-- ============================================================================
-- SQL_FIXES.sql — RAG AI Platform Supabase Remediation
-- ============================================================================
-- Purpose:    Fix 42501 permission denied errors and tighten RLS policies.
-- Safety:     READ-ONLY audit completed. No destructive operations below.
--             All changes are additive (GRANT) or policy replacements (DROP + CREATE).
-- Approval:   Run ONLY after user review and explicit approval.
-- Target:     Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- ============================================================================


-- ============================================================================
-- SECTION 1 — DIAGNOSTIC QUERIES (Run First — Safe, Read-Only)
-- Purpose: Verify current privilege state before applying any changes.
-- ============================================================================

-- 1A. Check current table privileges for all roles
SELECT
    table_name,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name IN ('users', 'conversations', 'messages', 'shared_documents')
ORDER BY table_name, grantee, privilege_type;

-- 1B. Verify RLS is enabled on all tables
SELECT
    schemaname,
    tablename,
    rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('users', 'conversations', 'messages', 'shared_documents');

-- 1C. List all current RLS policies
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd AS operation,
    qual AS using_expr,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, cmd;

-- 1D. Count rows currently in each table
SELECT 'users' AS tbl, COUNT(*) FROM public.users
UNION ALL
SELECT 'conversations', COUNT(*) FROM public.conversations
UNION ALL
SELECT 'messages', COUNT(*) FROM public.messages
UNION ALL
SELECT 'shared_documents', COUNT(*) FROM public.shared_documents;


-- ============================================================================
-- SECTION 2 — FIX 42501 PERMISSION DENIED ERRORS
-- ============================================================================
-- Root cause: GRANTs defined in supabase_schema.sql were never executed in
-- the live Supabase project. The Table Editor uses a direct Postgres connection
-- under the postgres role, which needs explicit GRANT USAGE + GRANT SELECT etc.
--
-- Security impact of these grants:
--   - GRANT to postgres: Allows the Table Editor to view tables. No external
--     access — postgres role is internal to Supabase infrastructure.
--   - GRANT to service_role: Allows the FastAPI backend (via service_role JWT)
--     to bypass RLS for admin operations. This was already working via
--     PostgREST; this grant makes it explicit and future-proof.
--   - GRANT to authenticated: Allows authenticated users (via anon/authenticated
--     JWT) to call PostgREST endpoints; RLS policies still control row access.
--   - GRANT to anon: RESTRICTED below — anon only gets SELECT on shared_documents.
--     Other tables get no anon grants. See Section 3.
-- ============================================================================

-- 2A. Grant schema usage (required before any table grants)
GRANT USAGE ON SCHEMA public TO postgres, authenticated, service_role;
-- Note: anon gets schema USAGE separately and only for shared_documents SELECT.
GRANT USAGE ON SCHEMA public TO anon;

-- 2B. Grant table-specific privileges with least privilege

-- public.users: authenticated users need SELECT (view profile); service_role needs ALL for admin ops
GRANT SELECT, UPDATE ON TABLE public.users TO authenticated;
GRANT ALL ON TABLE public.users TO postgres, service_role;

-- public.conversations: authenticated users need SELECT, INSERT, UPDATE, DELETE (their own rows — RLS enforces ownership)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.conversations TO authenticated;
GRANT ALL ON TABLE public.conversations TO postgres, service_role;

-- public.messages: authenticated users need SELECT, INSERT, DELETE (UPDATE not needed — messages aren't editable)
GRANT SELECT, INSERT, DELETE ON TABLE public.messages TO authenticated;
GRANT ALL ON TABLE public.messages TO postgres, service_role;

-- public.shared_documents: See Section 3 for anon vs authenticated distinction
-- authenticated users need SELECT, INSERT, DELETE (for uploaders and admins)
GRANT SELECT, INSERT, DELETE ON TABLE public.shared_documents TO authenticated;
GRANT ALL ON TABLE public.shared_documents TO postgres, service_role;
-- anon role gets SELECT only (read shared knowledge base documents when viewing as guest)
-- Revoke any existing broader grants first, then apply minimal grant
REVOKE INSERT, UPDATE, DELETE ON TABLE public.shared_documents FROM anon;
GRANT SELECT ON TABLE public.shared_documents TO anon;

-- 2C. Grant sequence access (needed for UUID generation in some configs)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO postgres, authenticated, service_role;

-- 2D. Grant function/routine access
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA public TO postgres, authenticated, service_role;

-- 2E. Set default privileges so future tables get the same grants automatically
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO postgres, authenticated, service_role;


-- ============================================================================
-- SECTION 3 — TIGHTEN RLS POLICIES ON shared_documents
-- ============================================================================
-- Current problem: INSERT and SELECT policies allow auth.role() = 'anon'.
-- This means an unauthenticated visitor can insert new document records into
-- the shared knowledge base directly via the Supabase JS client.
--
-- Architecture intent: shared_documents is a GLOBAL knowledge base visible to
-- all authenticated users, managed by admins/uploaders. Guests (anon) should
-- only be able to view the document list — not register new documents.
--
-- Security impact:
--   - Removing anon INSERT prevents unauthenticated document registration.
--   - Keeping SELECT open to anon allows the documents page to load for
--     unauthenticated visitors (if that is intended). If documents page
--     requires login, change SELECT to 'authenticated' only.
--   - The service_role bypass means the backend sync script is unaffected.
-- ============================================================================

-- 3A. Fix: Restrict INSERT on shared_documents to authenticated users only
DROP POLICY IF EXISTS "Authenticated users can upload shared documents" ON public.shared_documents;
CREATE POLICY "Authenticated users can upload shared documents"
    ON public.shared_documents
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');
-- Security: Removes anon INSERT. Only logged-in users can register documents.
-- Service role (FastAPI backend) bypasses RLS entirely — sync script unaffected.

-- 3B. Fix: Restrict SELECT on shared_documents to authenticated users only
-- (Remove this block if you want unauthenticated users to see the document list)
DROP POLICY IF EXISTS "Anyone authenticated can view shared documents" ON public.shared_documents;
CREATE POLICY "Authenticated users can view shared documents"
    ON public.shared_documents
    FOR SELECT
    USING (auth.role() = 'authenticated');
-- Security: Only logged-in users see the knowledge base document list.
-- If you want anon access (e.g., public demo), replace with:
--   USING (auth.role() = 'authenticated' OR auth.role() = 'anon');

-- 3C. Keep: DELETE policy is correctly scoped (uploader or service_role)
-- No change needed. Current policy:
--   USING (auth.uid() = uploader_id OR auth.jwt()->>'role' = 'service_role');
-- This is correct. Uploaders can delete their own documents; service_role (backend) can delete any.


-- ============================================================================
-- SECTION 4 — ADD MISSING UPDATE POLICY ON messages
-- ============================================================================
-- Current state: No UPDATE policy on messages table.
-- Effect: RLS blocks all UPDATE operations (safe by default, but implicit).
-- Recommendation: Explicitly document this restriction as a policy.
-- Note: Message editing is not a feature of this application, so no UPDATE
-- is intentional. Making it explicit is better than relying on implicit block.
-- ============================================================================

-- 4A. Explicitly deny all UPDATE on messages (optional, documents intent clearly)
-- This is informational only — RLS already blocks UPDATE without a policy.
-- If you later want to allow users to edit messages, replace this with the proper check.

-- DO NOT create an UPDATE policy for messages unless message editing is intended.
-- The absence of an UPDATE policy is the correct and secure state.


-- ============================================================================
-- SECTION 5 — VERIFICATION QUERIES (Run After Applying Fixes)
-- ============================================================================

-- 5A. Verify new privilege grants
SELECT
    table_name,
    grantee,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name IN ('users', 'conversations', 'messages', 'shared_documents')
  AND grantee IN ('postgres', 'anon', 'authenticated', 'service_role')
ORDER BY table_name, grantee, privilege_type;

-- 5B. Verify updated RLS policies
SELECT
    tablename,
    policyname,
    cmd AS operation,
    qual AS using_expr,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'shared_documents'
ORDER BY cmd;

-- 5C. Test: Can authenticated user read their own conversations?
-- (Run this in SQL Editor while authenticated — should return 0 or more rows, NOT error)
-- SELECT * FROM public.conversations LIMIT 5;

-- 5D. Test: Can anon insert a shared document? (Should now FAIL with RLS error)
-- SET LOCAL ROLE anon;
-- INSERT INTO public.shared_documents (document_id, filename, source, chunks, pages, uploaded_by)
-- VALUES ('test', 'test.pdf', 'test', 1, 1, 'anon_test');
-- Expected: ERROR: new row violates row-level security policy
-- ROLLBACK;

-- ============================================================================
-- END OF SQL_FIXES.sql
-- ============================================================================
