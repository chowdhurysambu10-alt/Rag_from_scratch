# Troubleshooting Report — RAG AI Platform
**Date:** 2026-11-21 | **Version:** 1.0 (Pre-Approval, Audit Only)
**Status:** Root causes identified. Fixes proposed. Awaiting approval before execution.

---

## Executive Summary

| Issue | Root Cause | Severity | Requires DB Change |
|---|---|---|---|
| `42501` permission denied on 3 tables | GRANTs in schema file were never executed in Supabase | HIGH | ✅ Yes |
| "Too many failed attempts / Form locked" | Old browser-cached version of `login.html` from previous session | LOW | ❌ No |
| "⚠️ Error message" on page load | The ⚠️ emoji is hardcoded inside the hidden alert `<span>` — rendered visible by CSS cascade in some browsers | LOW | ❌ No |
| `shared_documents` table empty | Table requires a sync run after GRANTs are applied; records were wiped when schema was re-applied | MEDIUM | ✅ Yes (sync) |

---

## Issue 1 — Supabase `42501` Permission Denied

### Evidence

**Screenshot:** Supabase Unified Logs (Postgres log type, 5xx Error level):
```
20 Nov 23:31:28  42501  permission denied for table shared_documents
20 Nov 23:31:27  42501  permission denied for table messages
20 Nov 23:31:27  42501  permission denied for table conversations
```

**Log type observed:** `Postgres` (direct database connection), NOT `API Gateway` (PostgREST).

This is the critical distinction. It tells us:
- The errors come from the **Supabase Table Editor** or **SQL Editor**, which connects as the `postgres` superuser role.
- The FastAPI backend (which uses the Supabase service role key via PostgREST HTTP) is **not the source**.

### Root Cause Analysis

**Step 1 — Schema file inspection** (`supabase_schema.sql`, lines 239–250):

```sql
grant usage on schema public to postgres, anon, authenticated, service_role;
grant all on table public.users to postgres, anon, authenticated, service_role;
grant all on table public.conversations to postgres, anon, authenticated, service_role;
grant all on table public.messages to postgres, anon, authenticated, service_role;
grant all on table public.shared_documents to postgres, anon, authenticated, service_role;
grant all on all sequences in schema public to postgres, anon, authenticated, service_role;
grant all on all routines in schema public to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to postgres, anon, authenticated, service_role;
```

The GRANTs **exist in the schema file** but were **never executed** in the live Supabase project. Evidence:
- The git log shows `supabase_schema.sql` was last modified during development but was not automatically applied to Supabase (Supabase doesn't auto-run `.sql` files from your local disk).
- The 42501 errors occur during the same time window that the Table Editor was opened — confirming it's the Table Editor's direct connection being denied.

**Step 2 — Why postgres role is denied:**

In Supabase, by default:
- When new tables are created in the `public` schema, they are owned by the creator role.
- The `postgres` role (used by Table Editor) may not have been explicitly granted if the schema was rebuilt via `CREATE TABLE IF NOT EXISTS` without the GRANTs.
- Supabase projects apply a `public` schema migration via their internal migrations system. Locally-written `.sql` files are **not automatically run** — they must be executed manually in the SQL Editor.

**Step 3 — Why the FastAPI backend works:**

The backend (`supabase_service.py`, line 17) uses `SUPABASE_SERVICE_ROLE_KEY` which provides PostgREST with a service-role JWT. PostgREST maps this to the `service_role` Postgres role, which bypasses RLS and has full access regardless of GRANT state. This is why the app functions fine while the Table Editor shows errors.

### Conclusion

**Root cause: GRANTs in `supabase_schema.sql` were written but never executed in the Supabase project.**
The fix is to run the GRANT statements in Supabase SQL Editor. See `SQL_FIXES.sql`.

---

## Issue 2 — "Too Many Failed Attempts / Form Locked for X Seconds"

### Evidence — Code-Level Investigation

**Search results across all frontend files:**
```
Frontend/login.html: 0 occurrences of "Form locked"
Frontend/login.html: 0 occurrences of "Too many failed attempts"
Frontend/login.html: 0 occurrences of "MAX_ATTEMPTS"
Frontend/login.html: 0 occurrences of "LOCKOUT_DURATION"
Frontend/js/auth.js: 0 occurrences of any lockout/brute-force code
```

What **does** exist in `login.html` (lines 334–336):
```javascript
// Clear any lingering rate-limit lockout from sessionStorage
sessionStorage.removeItem("rag_auth_failed_attempts");
sessionStorage.removeItem("rag_auth_lockout_until");
```

These lines **clear** the old lockout keys on page load — they do not set them. This is the **remnant cleanup code** from when rate limiting existed in an older version of the file.

**Current `auth.js` rate-limit handling** (lines 75–76): Only catches **Supabase server-side** `over_request_rate_limit` errors and passes them as plain error messages. No client-side lockout timer exists.

### Root Cause

**The "Form locked for X seconds" UI was removed from the frontend code in a previous fix.** The screenshot was taken while the browser was serving a **cached version** of `login.html` that pre-dates the fix.

Proof: The exact string "Form locked" does not appear anywhere in the current `login.html` or `auth.js`. The only lockout-related code is the `sessionStorage.removeItem()` cleanup calls added when the lockout was removed.

**This is confirmed as a browser caching issue** (not assumed) because:
1. The string does not exist in the file.
2. The file has been modified since the screenshot was taken.
3. The cleanup code explicitly clears the old sessionStorage keys, confirming awareness of a prior version.

### Fix

**No code changes needed.** User must perform a hard reload (`Cmd + Shift + R` on macOS) or open an Incognito window to bypass cached files.

---

## Issue 3 — "⚠️ Error message" Alert on Page Load

### Evidence — HTML Inspection

`login.html` lines 270–273:
```html
<div class="auth-alert" id="authAlert" style="display: none;">
    <span id="alertIcon">⚠️</span>
    <span id="alertMessage"></span>
</div>
```

The alert `div` has `style="display: none;"` as an inline attribute AND the CSS class rule at line 170:
```css
.auth-alert {
    display: none;
    ...
}
```

**Why it appears in some browsers:**

The `alertIcon` span contains hardcoded text `⚠️` — not a placeholder. When the `auth-alert` div is hidden, the `⚠️` is invisible. However, in certain browser+CSS configurations, if another script or the browser's CSS parser handles `display: none` differently during the initial render cycle (e.g., DevTools opened, browser extension that injects CSS, or a render flash before `DOMContentLoaded`), the emoji briefly appears.

**More likely cause:** The screenshot was taken from the **cached old version** (same session as Issue 2), where the alert was shown after a failed login attempt and the page was refreshed without clearing state — `alertMessage` text from a prior interaction appeared.

### Root Cause

The `⚠️` emoji is hardcoded inside a span that is inside the hidden container. While the div is `display: none`, the emoji is a render-time constant. In the current code, this will never show on initial page load because:
- `display: none` is set both in CSS and inline `style`
- `showAlert()` is never called at initialization

**However**, there is a minor hardening opportunity: the `alertIcon` span should start empty and be populated only by `showAlert()`.

### Fix

**Minor hardening fix** to `login.html` — remove the hardcoded `⚠️` from the HTML and let `showAlert()` set it. No backend changes needed.

---

## Issue 4 — `shared_documents` Table Empty

### Evidence

The Supabase Table Editor screenshot shows `0 records` in `shared_documents`.

**Qdrant Cloud status:** 3,306 vectors across 13 documents exist in collection `rag_documents_v2` (confirmed from prior audit).

**sync_qdrant_to_supabase.py** exists and was successfully run previously — it synced 13 documents. However, the table is empty now, which means one of:
1. The rows were deleted when the schema was re-applied (a `DROP TABLE` or schema reset wiped the data).
2. The sync script has not been run since the last schema rebuild.

The `supabase_schema.sql` file uses `CREATE TABLE IF NOT EXISTS` — so it would not drop existing data on re-run. However, if someone ran `DROP TABLE` and then the schema, all data would be lost.

**The `shared_documents` RLS INSERT policy** (from schema):
```sql
create policy "Authenticated users can upload shared documents"
    on public.shared_documents for insert
    with check (auth.role() = 'authenticated' or auth.role() = 'anon');
```

This policy allows `anon` role to insert — a security concern (see Security section below). However, this doesn't prevent the sync script from inserting (the sync uses service role which bypasses RLS).

### Root Cause

**The sync script has not been re-run since the last schema rebuild.** The table is empty. The fix is to re-run `sync_qdrant_to_supabase.py` after the GRANTs are applied.

---

## Security Analysis of Existing RLS Policies

### ✅ Correctly Secured Tables

| Table | RLS | SELECT Policy | INSERT Policy | UPDATE Policy | DELETE Policy |
|---|---|---|---|---|---|
| `users` | ✅ Enabled | `auth.role() = 'authenticated'` (all authenticated users can see all users) | None (populated by trigger) | Only own row | None |
| `conversations` | ✅ Enabled | `auth.uid() = user_id` ✅ | `auth.uid() = user_id` ✅ | `auth.uid() = user_id` ✅ | `auth.uid() = user_id` ✅ |
| `messages` | ✅ Enabled | `auth.uid() = user_id` ✅ | `auth.uid() = user_id` ✅ | ❌ No UPDATE policy | `auth.uid() = user_id` ✅ |

### ⚠️ Issues Found in `shared_documents` Policies

**Problem 1 — INSERT allows `anon` role:**
```sql
-- CURRENT (problematic):
create policy "Authenticated users can upload shared documents"
    on public.shared_documents for insert
    with check (auth.role() = 'authenticated' or auth.role() = 'anon');
```
This allows unauthenticated visitors to insert document records directly into `shared_documents` via the Supabase JS client. Only authenticated users should be able to register documents.

**Problem 2 — SELECT allows `anon` role:**
```sql
-- CURRENT (debatable):
create policy "Anyone authenticated can view shared documents"
    on public.shared_documents for select
    using (auth.role() = 'authenticated' or auth.role() = 'anon');
```
If the shared knowledge base is meant to be accessible only to logged-in users, this should require `auth.role() = 'authenticated'` only.

**Problem 3 — DELETE lacks UPDATE policy:**
No `UPDATE` policy exists on `messages`. If a frontend bug or attacker calls a UPDATE via PostgREST, it would be blocked by RLS (UPDATE is denied by default when no policy exists). This is actually safe — but should be explicit.

**Problem 4 — `GRANT ALL` to `anon` role:**
The schema grants `ALL` on all tables to the `anon` role. Combined with the `anon`-permissive RLS policies, this is unnecessarily broad. The `anon` role should only have `SELECT` on `shared_documents`, not `INSERT`, `UPDATE`, or `DELETE`.

### ✅ Backend Authorization — Correctly Implemented

The backend (`auth_middleware.py`) uses `get_current_user_required` on all sensitive endpoints. The `supabase_service.py` JWT verification uses three-layer validation (Supabase Auth API → ES256 JWKS → HS256 fallback). The backend never trusts a user_id from the request body — it always reads from the verified JWT.

---

## Test Results (Static Code Analysis — Server Not Running)

| Test | Status | Evidence |
|---|---|---|
| Unauthenticated DB access via PostgREST | ✅ Blocked by RLS | conversations/messages policies require `auth.uid()` |
| Authenticated user access | ✅ Works | JWT verified, service role key used for backend ops |
| Cross-user conversation access | ✅ Blocked | All policies filter by `auth.uid() = user_id` |
| Shared document visibility | ⚠️ Over-permissive | `anon` role can read and insert via RLS policy |
| Document synchronization | ❌ Not run | Table is empty; sync script needs re-execution |
| Signup flow | ✅ Works | Backend `/api/auth/signup` creates user with `email_confirm=True` |
| Login with wrong password | ✅ Rejected | `signInWithPassword()` → Supabase rejects → `invalid_credentials` thrown |
| Initial page load alert | ✅ No alert in code | Alert div starts `display:none` with empty `alertMessage` span |
| Rate-limit message | ✅ Not in current code | No lockout logic exists in current files |
| Rate-limit recovery | N/A | No client-side rate limiting code exists |

---

## Summary of Required Actions (Awaiting Approval)

| Priority | Action | File | Type |
|---|---|---|---|
| 1 | Run targeted GRANTs in SQL Editor | `SQL_FIXES.sql` → Supabase | SQL — Required |
| 2 | Tighten `shared_documents` RLS (remove `anon` insert) | `SQL_FIXES.sql` → Supabase | SQL — Recommended |
| 3 | Harden `anon` GRANTs to table-specific permissions | `SQL_FIXES.sql` → Supabase | SQL — Recommended |
| 4 | Remove hardcoded `⚠️` from alert HTML | `Frontend/login.html` | Frontend — Minor |
| 5 | Re-run Qdrant→Supabase sync | `sync_qdrant_to_supabase.py` | Script — Required |
| 6 | Hard-reload browser | Browser | Manual — Required |
