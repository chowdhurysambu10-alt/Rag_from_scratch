/**
 * RAG AI - Supabase Client Factory
 * Initializes and exposes the official Supabase JavaScript client.
 * Uses public publishable credentials with automatic session persistence and token refresh.
 */

const SUPABASE_PUBLIC_URL = "https://egyqysoxmootmtrgcuux.supabase.co";
const SUPABASE_PUBLIC_ANON_KEY = "sb_publishable_yZlck3k75JWSqVihRX6pog_pBcwKQRN";

window.supabaseClient = null;

function getSupabaseClient() {
    if (window.supabaseClient) return window.supabaseClient;

    if (window.supabase && typeof window.supabase.createClient === "function") {
        try {
            window.supabaseClient = window.supabase.createClient(
                SUPABASE_PUBLIC_URL,
                SUPABASE_PUBLIC_ANON_KEY,
                {
                    auth: {
                        persistSession: true,
                        autoRefreshToken: true,
                        detectSessionInUrl: true,
                        storage: window.localStorage
                    }
                }
            );
            return window.supabaseClient;
        } catch (err) {
            console.error("Failed to initialize Supabase client:", err);
            return null;
        }
    }
    return null;
}

// Auto-initialize as soon as script runs
if (window.supabase) {
    getSupabaseClient();
} else {
    window.addEventListener("DOMContentLoaded", () => {
        getSupabaseClient();
    });
}

window.initSupabaseClient = async function () {
    const client = getSupabaseClient();
    if (client) return client;

    // Retry if CDN script was slightly delayed
    for (let i = 0; i < 5; i++) {
        await new Promise(r => setTimeout(r, 100));
        const c = getSupabaseClient();
        if (c) return c;
    }
    return null;
};
