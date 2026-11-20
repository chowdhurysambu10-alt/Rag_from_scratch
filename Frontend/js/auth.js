/**
 * RAG AI - Production Supabase Authentication & Session Management
 * Enforces cryptographic auth, rejects invalid passwords, manages tokens,
 * handles email verification, and protects all application routes.
 */

const STORAGE_AUTH_USER = "rag_ai_auth_user_v2";
const STORAGE_AUTH_TOKEN = "rag_ai_auth_token_v2";

const authService = {
    /**
     * Get the currently authenticated user from storage.
     */
    getUser() {
        try {
            const raw = localStorage.getItem(STORAGE_AUTH_USER);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    },

    /**
     * Get the current verified Supabase JWT Bearer token.
     */
    getToken() {
        return localStorage.getItem(STORAGE_AUTH_TOKEN) || "";
    },

    /**
     * Returns standard Authorization headers for protected backend endpoints.
     */
    getAuthHeaders() {
        const token = this.getToken();
        const headers = {
            "Content-Type": "application/json"
        };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
        return headers;
    },

    /**
     * Authenticate an existing user with Email and Password using Supabase Auth.
     * Strictly rejects wrong passwords and non-existent accounts.
     */
    async signIn(email, password) {
        if (!email || !email.trim()) {
            throw new Error("Please enter your email address.");
        }
        if (!password) {
            throw new Error("Please enter your password.");
        }

        const client = await window.initSupabaseClient();
        if (!client) {
            throw new Error("Network error: Authentication service is unavailable. Please check your connection.");
        }

        const { data, error } = await client.auth.signInWithPassword({
            email: email.trim().toLowerCase(),
            password: password
        });

        if (error) {
            const errCode = error.code || "";
            const msg = (error.message || "").toLowerCase();
            if (errCode === "invalid_credentials" || msg.includes("invalid login credentials") || msg.includes("invalid_grant")) {
                throw new Error("Incorrect email address or password. Please try again.");
            }
            if (msg.includes("email not confirmed")) {
                throw new Error("Your email address has not been confirmed yet. Please check your inbox for the verification link.");
            }
            if (errCode === "over_request_rate_limit" || msg.includes("too many requests") || msg.includes("rate limit")) {
                throw new Error("Too many sign-in attempts. Please wait a few moments before trying again.");
            }
            throw new Error(error.message || "Failed to sign in. Please verify your credentials.");
        }

        if (!data || !data.session || !data.session.access_token) {
            throw new Error("Authentication failed: No active session received from server.");
        }

        // Persist valid Supabase session
        this.saveSession(data.session.user, data.session.access_token);
        return data;
    },

    /**
     * Secure user registration using Supabase Auth.
     * Enforces min 8 character password, prevents duplicate calls, and handles email rate limits.
     */
    async signUp(email, password) {
        const cleanEmail = email.trim().toLowerCase();
        if (!cleanEmail || !cleanEmail.includes("@")) {
            throw new Error("Please enter a valid email address.");
        }
        if (!password || password.length < 8) {
            throw new Error("Password must be at least 8 characters in length.");
        }

        // 1. First, attempt backend registration endpoint.
        // This creates the user in Supabase with email_confirm=True, completely avoiding Supabase's rate-limited free mailer.
        try {
            const res = await fetch("http://127.0.0.1:8000/api/auth/signup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: cleanEmail, password: password })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.session && data.session.access_token) {
                    this.saveSession(data.user, data.session.access_token);
                    const client = await window.initSupabaseClient();
                    if (client && client.auth) {
                        try {
                            await client.auth.setSession({
                                access_token: data.session.access_token,
                                refresh_token: data.session.refresh_token
                            });
                        } catch (e) {
                            console.debug("Client setSession note:", e);
                        }
                    }
                    return {
                        needsEmailVerification: false,
                        user: data.user,
                        session: data.session
                    };
                } else {
                    return {
                        needsEmailVerification: false,
                        user: data.user,
                        message: data.message
                    };
                }
            } else {
                const errData = await res.json().catch(() => ({}));
                const detail = errData.detail || "";
                if (res.status === 409 || detail.includes("already exists") || detail.includes("already registered")) {
                    throw new Error("An account with this email address already exists. Please sign in instead.");
                }
                if (res.status === 429 || detail.includes("rate limit")) {
                    throw new Error("Signup rate limit reached. Please wait a moment before trying again.");
                }
                if (detail) {
                    throw new Error(detail);
                }
            }
        } catch (fetchErr) {
            // Rethrow explicit business validation and conflict errors
            if (fetchErr.message && (
                fetchErr.message.includes("already exists") ||
                fetchErr.message.includes("at least 8 characters") ||
                fetchErr.message.includes("valid email")
            )) {
                throw fetchErr;
            }
            console.debug("Backend signup endpoint note, attempting direct client signup:", fetchErr);
        }

        // 2. Direct client signup fallback
        const client = await window.initSupabaseClient();
        if (!client) {
            throw new Error("Network error: Unable to reach authentication server. Please check your internet connection.");
        }

        const { data, error } = await client.auth.signUp({
            email: cleanEmail,
            password: password
        });

        if (error) {
            const errCode = error.code || "";
            const msg = (error.message || "").toLowerCase();

            if (errCode === "over_email_send_rate_limit" || msg.includes("email rate limit exceeded") || msg.includes("rate limit")) {
                throw new Error("Supabase email rate limit exceeded. Please ensure backend is running or disable 'Confirm email' in Supabase Dashboard.");
            }
            if (errCode === "over_request_rate_limit" || msg.includes("too many requests")) {
                throw new Error("Too many registration requests. Please wait a moment before trying again.");
            }
            if (msg.includes("already registered") || msg.includes("user_already_exists")) {
                throw new Error("An account with this email address already exists. Please sign in instead.");
            }
            if (msg.includes("password")) {
                throw new Error("Password must be at least 8 characters and sufficiently secure.");
            }
            throw new Error(error.message || "Failed to create account. Please check your details.");
        }

        // If email confirmation is enabled in Supabase, data.session is null until verified
        if (data && data.user && !data.session) {
            return {
                needsEmailVerification: true,
                email: data.user.email
            };
        }

        if (data && data.session) {
            this.saveSession(data.session.user, data.session.access_token);
            return {
                needsEmailVerification: false,
                user: data.session.user,
                session: data.session
            };
        }

        return data;
    },

    /**
     * Request a password reset link.
     */
    async resetPassword(email) {
        if (!email || !email.trim() || !email.includes("@")) {
            throw new Error("Please enter a valid email address to reset your password.");
        }
        const client = await window.initSupabaseClient();
        if (!client) {
            throw new Error("Authentication service is unavailable.");
        }

        const { error } = await client.auth.resetPasswordForEmail(email.trim().toLowerCase(), {
            redirectTo: window.location.origin + "/Frontend/login.html"
        });
        if (error) {
            throw new Error(error.message || "Failed to send reset email.");
        }
        return true;
    },

    /**
     * Save verified Supabase session to localStorage.
     */
    saveSession(user, token) {
        localStorage.setItem(STORAGE_AUTH_USER, JSON.stringify({
            id: user.id,
            email: user.email || "user@example.com",
            role: user.role || "authenticated",
            isGuest: false
        }));
        if (token) {
            localStorage.setItem(STORAGE_AUTH_TOKEN, token);
        }
    },

    /**
     * Sign out the user, invalidate the session in Supabase, and clear local state.
     */
    async signOut() {
        try {
            const client = await window.initSupabaseClient();
            if (client) {
                await client.auth.signOut();
            }
        } catch (e) {
            console.debug("Sign out note:", e);
        }

        localStorage.removeItem(STORAGE_AUTH_USER);
        localStorage.removeItem(STORAGE_AUTH_TOKEN);
        sessionStorage.clear();

        window.location.href = "login.html";
    },

    /**
     * Protect application routes.
     * Unauthenticated users are redirected to login.html.
     * Authenticated users are redirected away from login.html to index.html.
     */
    async checkRouteProtection() {
        const path = window.location.pathname;
        const isAuthPage = path.endsWith("login.html") || path.endsWith("/login");

        const client = await window.initSupabaseClient();
        if (!client) {
            if (!isAuthPage) {
                window.location.href = "login.html";
            }
            return;
        }

        // Check active session from Supabase SDK
        const { data: { session } } = await client.auth.getSession();

        if (session && session.user && session.access_token) {
            this.saveSession(session.user, session.access_token);
            if (isAuthPage) {
                window.location.href = "index.html";
                return;
            }
        } else {
            // No valid active session
            localStorage.removeItem(STORAGE_AUTH_USER);
            localStorage.removeItem(STORAGE_AUTH_TOKEN);
            if (!isAuthPage) {
                window.location.href = "login.html";
                return;
            }
        }

        // Listen for real-time auth state changes
        client.auth.onAuthStateChange((event, newSession) => {
            if (event === "SIGNED_OUT" || !newSession) {
                localStorage.removeItem(STORAGE_AUTH_USER);
                localStorage.removeItem(STORAGE_AUTH_TOKEN);
                if (!isAuthPage) {
                    window.location.href = "login.html";
                }
            } else if (newSession && newSession.user) {
                this.saveSession(newSession.user, newSession.access_token);
            }
        });

        // Render user widget in sidebar on application pages
        if (!isAuthPage) {
            this.renderSidebarProfile();
        }
    },

    /**
     * Render User profile widget and Sign Out button in the sidebar footer.
     */
    renderSidebarProfile() {
        const user = this.getUser();
        if (!user) return;

        let userWidget = document.getElementById("sidebarUserWidget");
        if (!userWidget) {
            const sidebarFooter = document.querySelector(".sidebar-footer");
            if (!sidebarFooter) return;

            userWidget = document.createElement("div");
            userWidget.id = "sidebarUserWidget";
            userWidget.className = "sidebar-user-widget";
            sidebarFooter.appendChild(userWidget);
        }

        const email = user.email || "User";
        const initial = email.charAt(0).toUpperCase();
        const roleLabel = "Member";

        userWidget.innerHTML = `
            <div class="user-profile-row">
                <div class="user-avatar-badge">${escapeHtml(initial)}</div>
                <div class="user-info-text">
                    <span class="user-email-span" title="${escapeHtml(email)}">${escapeHtml(email)}</span>
                    <span class="user-role-tag member">${escapeHtml(roleLabel)}</span>
                </div>
                <button type="button" class="user-logout-btn" id="logoutBtn" title="Sign Out">
                    <span style="font-size: 14px;">↪</span>
                </button>
            </div>
        `;

        const logoutBtn = document.getElementById("logoutBtn");
        if (logoutBtn) {
            logoutBtn.onclick = () => this.signOut();
        }
    }
};

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", () => {
    authService.checkRouteProtection();
});

window.authService = authService;
