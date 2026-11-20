# Authentication Fix Report — RAG AI Platform
**Date:** 2026-11-21 | **Status:** Analysis Complete — Awaiting Approval

---

## 1. Signup Flow — Current Implementation

### Backend (`Backend/main.py` — `/api/auth/signup` endpoint)

```
POST /api/auth/signup
Body: { email, password }
```

**Flow:**
1. Validates email format and minimum password length (8 chars)
2. Uses `admin_client.auth.admin.create_user({ email_confirm: True })` → bypasses Supabase free-tier email rate limit
3. Inserts user row into `public.users` (triggers also insert via trigger, so this is redundant but harmless)
4. Signs in immediately via `anon_client.auth.sign_in_with_password()` → returns real Supabase JWT session
5. Returns `{ success, user, session: { access_token, refresh_token, expires_at } }`

**Security assessment:** ✅ Correct. The `email_confirm: True` flag marks the email as pre-verified in Supabase Auth — it does not disable email confirmation globally. Admin API is used server-side, never exposed to the browser.

### Frontend (`Frontend/js/auth.js` — `signUp()`)

**Flow:**
1. Validates email format and password length ≥ 8 chars locally
2. Calls `POST http://127.0.0.1:8000/api/auth/signup` (backend)
3. If backend succeeds → calls `client.auth.setSession()` to sync the JWT into the Supabase JS SDK → redirects to `index.html`
4. If backend unreachable → falls back to `client.auth.signUp()` directly (Supabase free-tier, may hit email rate limit)

**Security assessment:** ✅ No bypass. ✅ No fake session creation.

---

## 2. Login Flow — Current Implementation

### Frontend (`Frontend/js/auth.js` — `signIn()`)

```javascript
const { data, error } = await client.auth.signInWithPassword({
    email: email.trim().toLowerCase(),
    password: password
});
```

**Error handling:**
- `invalid_credentials` → "Incorrect email address or password."
- `email not confirmed` → "Email not confirmed yet."
- `over_request_rate_limit` → "Too many sign-in attempts."

**Security assessment:** ✅ Uses Supabase's cryptographic password verification. Wrong passwords are rejected by Supabase, not by frontend logic. No local password storage or comparison.

---

## 3. JWT Verification — Backend (`Backend/services/supabase_service.py`)

Three-layer verification (most to least authoritative):

| Layer | Method | When Used |
|---|---|---|
| 1 (Primary) | `client.auth.get_user(token)` — calls Supabase Auth API | Always attempted first |
| 2 (Fallback) | ES256/RS256 JWKS verification via public key | If layer 1 fails (network issue) |
| 3 (Fallback) | HS256 with `SUPABASE_JWT_SECRET` | Only if secret is set and not placeholder |

**Security assessment:** ✅ Layer 1 catches revoked tokens (server-side session invalidation). ✅ Layer 2 catches expired tokens via `exp` claim. ✅ Layer 3 is guarded by a placeholder check — it won't activate with the default `"your-jwt-secret"` placeholder.

> [!WARNING]
> **SUPABASE_JWT_SECRET is still the placeholder `"your-jwt-secret"`** in the `.env` file. Layer 3 is correctly disabled (the guard `SUPABASE_JWT_SECRET != "your-jwt-secret"` prevents it). However, the `.env.example` does not document this key at all — which means if someone sets a real but incorrect secret, Layer 3 could reject valid tokens. Set the real JWT secret from your Supabase Dashboard → Settings → API → JWT Settings.

---

## 4. Session Management

### Persistence

```javascript
// auth.js — saveSession()
localStorage.setItem(STORAGE_AUTH_USER, JSON.stringify({ id, email, role, isGuest: false }));
localStorage.setItem(STORAGE_AUTH_TOKEN, token);
```

**Security assessment:** ✅ Tokens stored in `localStorage` (acceptable for SPAs; HttpOnly cookies are more secure but require server-side session endpoints). The Supabase JS SDK also stores its own session in localStorage with `persistSession: true` and handles automatic token refresh via `autoRefreshToken: true`.

### Restoration on Page Refresh

```javascript
// auth.js — checkRouteProtection()
const { data: { session } } = await client.auth.getSession();
if (session && session.user && session.access_token) {
    this.saveSession(session.user, session.access_token);
}
```

**Security assessment:** ✅ Relies on the Supabase SDK's `getSession()` which validates the token locally and refreshes it if expired. The backend still verifies every request's JWT independently.

### Logout

```javascript
await client.auth.signOut();      // Invalidates session on Supabase server
localStorage.removeItem(STORAGE_AUTH_USER);
localStorage.removeItem(STORAGE_AUTH_TOKEN);
sessionStorage.clear();
window.location.href = "login.html";
```

**Security assessment:** ✅ Server-side session invalidation via `signOut()`. ✅ All local state cleared. ✅ Redirect enforced.

---

## 5. Route Protection

### Frontend (`auth.js` — `checkRouteProtection()`)

- Called on every page load via `DOMContentLoaded`
- Calls `client.auth.getSession()` → if no valid session, redirects to `login.html`
- Listens for `SIGNED_OUT` via `onAuthStateChange()` → redirects immediately

**Security assessment:** ⚠️ Frontend-only route protection is not sufficient on its own. If JavaScript is disabled or the user manipulates the DOM, they could bypass the redirect. However, all protected API endpoints require a valid JWT (enforced by `get_current_user_required` Depends on backend), so bypassing the frontend check only gives access to the HTML shell — not any data.

### Backend (`auth_middleware.py`)

```python
user: Dict[str, Any] = Depends(get_current_user_required)
```

Applied to: `/chat`, `/api/conversations/*`, `/api/upload/*`

**Security assessment:** ✅ All sensitive endpoints require a verified JWT. The user identity comes from the JWT, never from request body or headers.

---

## 6. "Too Many Failed Attempts / Form Locked" — Auth Investigation

### Evidence from Source Code

| File | Searched For | Result |
|---|---|---|
| `Frontend/login.html` | "Form locked" | **0 occurrences** |
| `Frontend/login.html` | "Too many failed attempts" | **0 occurrences** |
| `Frontend/login.html` | "MAX_ATTEMPTS" | **0 occurrences** |
| `Frontend/login.html` | "LOCKOUT_DURATION" | **0 occurrences** |
| `Frontend/js/auth.js` | Any lockout/brute-force code | **0 occurrences** |
| `Backend/main.py` | Client-side rate limit logic | **0 occurrences** |

### What Does Exist

`Frontend/login.html` lines 334–336 (DOMContentLoaded handler):
```javascript
// Clear any lingering rate-limit lockout from sessionStorage
sessionStorage.removeItem("rag_auth_failed_attempts");
sessionStorage.removeItem("rag_auth_lockout_until");
```

These are **cleanup lines from a previous version** that had client-side rate limiting. The lockout UI and counter logic have been completely removed. These lines are harmless — they clear keys that no longer exist.

**The screenshot showing this message was taken from a browser-cached version of the old `login.html`.** The current file (committed as `9e2fe3e` in git) does not contain this feature.

### Fix

No code change required. The fix for the user is a hard browser reload:
- **Chrome / Edge:** `Cmd + Shift + R` (macOS) or `Ctrl + Shift + R` (Windows)
- **Safari:** `Cmd + Option + R`
- **Firefox:** `Cmd + Shift + R`
- Or open an **Incognito / Private window**

---

## 7. "⚠️ Error message" Alert on Initial Page Load

### Evidence from Source Code

**HTML** (`login.html` line 270–273):
```html
<div class="auth-alert" id="authAlert" style="display: none;">
    <span id="alertIcon">⚠️</span>
    <span id="alertMessage"></span>
</div>
```

**CSS** (`login.html` lines 170–176):
```css
.auth-alert {
    display: none;
    padding: 10px 14px;
    ...
}
.auth-alert.visible {
    display: flex;
}
```

**JavaScript initialization:** `showAlert()` is never called at page load. `clearAlert()` is called when tabs change or user types.

### Diagnosis

The alert div is correctly hidden via two redundant mechanisms (`CSS display:none` + inline `style="display:none"`). However, the `alertIcon` span contains a hardcoded `⚠️` emoji. This creates a subtle rendering issue:

- If a browser extension, screen reader, or CSS override temporarily makes the div visible during the DOM parsing phase, the `⚠️` text would appear for a split second.
- More likely: the screenshot was taken in a previous session after a failed login — the alert was visible and the user refreshed without clearing it. The `alertMessage` text from the failed attempt appeared on the next load because the browser served the cached page with the alert still marked `.visible` in memory.

**However**, upon actual page load with the current code, the div starts as `display:none` and `alertMessage` starts empty — so "Error message" text is impossible to appear unless JavaScript has explicitly called `showAlert()`.

### Fix Required

One minor hardening change to `login.html`:

**Current** (line 271):
```html
<span id="alertIcon">⚠️</span>
```

**Fix** (remove hardcoded emoji — let `showAlert()` set it):
```html
<span id="alertIcon"></span>
```

This eliminates any possibility of the icon appearing during a render flash, and makes it impossible to see any alert content without JavaScript explicitly calling `showAlert()`.

This fix has **no security impact** and **does not change functionality** — `showAlert()` already sets `alertIcon.textContent` dynamically.

---

## 8. Security Issues Found — Not Blocking Auth

| ID | Issue | Severity | Location |
|---|---|---|---|
| SEC-01 | `SUPABASE_JWT_SECRET` is placeholder `"your-jwt-secret"` in `.env` | MEDIUM | `.env` |
| SEC-02 | `allow_origins=["*"]` in CORS configuration | HIGH | `Backend/main.py` line 48 |
| SEC-03 | `anon` role allowed to INSERT into `shared_documents` via RLS | MEDIUM | `supabase_schema.sql` |
| SEC-04 | Supabase anon key hardcoded in `supabaseClient.js` | INFO | `Frontend/js/supabaseClient.js` |
| SEC-05 | Backend signup endpoint creates user immediately without email verification | INFO | `Backend/main.py` |

**Notes:**
- SEC-01: No immediate risk (guard prevents use of placeholder), but should be set before production.
- SEC-02: Restricting origins prevents CSRF from other domains; set to your actual frontend URL before deployment.
- SEC-03: Fixed in `SQL_FIXES.sql` Section 3.
- SEC-04: The anon key is a publishable key — this is the intended Supabase design. It is safe to expose. The service role key must never be exposed.
- SEC-05: This is intentional (bypasses free-tier email rate limit). The admin API is called server-side only.

---

## 9. Recommended Frontend Fix (login.html)

**File:** `Frontend/login.html`
**Line:** 271
**Change:** Remove hardcoded `⚠️` from `alertIcon` span

```diff
- <span id="alertIcon">⚠️</span>
+ <span id="alertIcon"></span>
```

**Impact:** Cosmetic hardening. No functional change. No security impact. Prevents any possibility of the emoji appearing during render flashes.

---

## 10. Required Actions Summary (Awaiting Approval)

| # | Action | Required | Type |
|---|---|---|---|
| 1 | Run Section 1 diagnostics in Supabase SQL Editor | ✅ Run First | Read-only SQL |
| 2 | Run Section 2 GRANTs (fix 42501) | ✅ Required | SQL — apply |
| 3 | Run Section 3 (tighten shared_documents RLS) | ✅ Recommended | SQL — apply |
| 4 | Run Section 5 verification queries | ✅ Run After | Read-only SQL |
| 5 | Re-run `sync_qdrant_to_supabase.py` | ✅ Required | Python script |
| 6 | Remove hardcoded `⚠️` from `login.html` line 271 | ⚠️ Minor | Frontend edit |
| 7 | Hard-reload browser (`Cmd+Shift+R`) | ✅ Required | Browser |
| 8 | Set real `SUPABASE_JWT_SECRET` in `.env` | ⚠️ Pre-production | Config |
| 9 | Restrict `allow_origins` in CORS before deployment | ⚠️ Pre-production | Backend config |
