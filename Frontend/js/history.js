/**
 * RAG AI - Conversation History Manager
 * Manages user-isolated persistent conversation sessions using Supabase & LocalStorage.
 * Ensures User A can NEVER view or access User B's conversations.
 */

class ConversationHistory {
    constructor() {
        this.conversations = this.loadAll();
        // Sync with Supabase on startup
        if (typeof window !== "undefined") {
            setTimeout(() => this.syncRemote(), 500);
        }
    }

    /**
     * Get storage key scoped to current authenticated user.
     */
    getStorageKey() {
        const user = window.authService ? window.authService.getUser() : null;
        const uid = user && user.id ? user.id : "guest";
        return `rag_ai_convs_v3_${uid}`;
    }

    getActiveKey() {
        const user = window.authService ? window.authService.getUser() : null;
        const uid = user && user.id ? user.id : "guest";
        return `rag_ai_active_id_${uid}`;
    }

    /**
     * Load all saved conversations for the current user.
     */
    loadAll() {
        try {
            const raw = localStorage.getItem(this.getStorageKey());
            if (!raw) return [];
            const list = JSON.parse(raw);
            return Array.isArray(list) ? list : [];
        } catch (e) {
            console.error("Failed to parse conversations from storage:", e);
            return [];
        }
    }

    /**
     * Save current conversation list for the active user.
     */
    saveAll() {
        try {
            localStorage.setItem(this.getStorageKey(), JSON.stringify(this.conversations));
        } catch (e) {
            console.error("Failed to save conversations to storage:", e);
        }
    }

    /**
     * Sync conversations from Supabase backend.
     */
    async syncRemote() {
        try {
            if (window.ragApi && typeof window.ragApi.getConversations === "function") {
                const remoteList = await window.ragApi.getConversations();
                if (Array.isArray(remoteList) && remoteList.length > 0) {
                    // Merge remote conversations into local state
                    const merged = [...this.conversations];
                    for (const r of remoteList) {
                        const existing = merged.find(c => c.id === r.id);
                        if (!existing) {
                            merged.push({
                                id: r.id,
                                title: r.title || "Conversation",
                                createdAt: new Date(r.created_at).getTime() || Date.now(),
                                updatedAt: new Date(r.updated_at).getTime() || Date.now(),
                                messages: []
                            });
                        } else {
                            existing.title = r.title || existing.title;
                        }
                    }
                    this.conversations = merged.sort((a, b) => b.updatedAt - a.updatedAt);
                    this.saveAll();
                    if (typeof window.renderSidebarHistory === "function") {
                        window.renderSidebarHistory();
                    }
                }
            }
        } catch (err) {
            console.debug("Remote conversations sync notice:", err);
        }
    }

    /**
     * Get the active conversation ID.
     */
    getActiveId() {
        return localStorage.getItem(this.getActiveKey()) || null;
    }

    /**
     * Ensure an active conversation and persistent session ID exist.
     */
    async ensureActiveSessionId() {
        this.conversations = this.loadAll();
        let activeId = this.getActiveId();
        let conv = activeId ? this.conversations.find(c => c.id === activeId) : null;
        if (!activeId || !conv) {
            try {
                if (window.ragApi && typeof window.ragApi.createConversation === "function") {
                    const res = await window.ragApi.createConversation("New Conversation");
                    activeId = res ? res.id : ("session_" + Date.now());
                } else {
                    activeId = "session_" + Date.now();
                }
            } catch {
                activeId = "session_" + Date.now();
            }
            this.createConversation(activeId, "New Conversation");
        }
        return activeId;
    }

    /**
     * Set the active conversation ID.
     */
    setActiveId(id) {
        if (id) {
            localStorage.setItem(this.getActiveKey(), id);
        } else {
            localStorage.removeItem(this.getActiveKey());
        }
    }

    /**
     * Get the currently active conversation object.
     */
    getActiveConversation() {
        const activeId = this.getActiveId();
        if (!activeId) return null;
        return this.conversations.find(c => c.id === activeId) || null;
    }

    /**
     * Create and record a new conversation.
     */
    createConversation(sessionId, initialTitle = "New Conversation") {
        const newConv = {
            id: sessionId,
            title: initialTitle,
            createdAt: Date.now(),
            updatedAt: Date.now(),
            messages: []
        };

        this.conversations.unshift(newConv);
        this.saveAll();
        this.setActiveId(sessionId);

        // Async remote sync
        if (window.ragApi && typeof window.ragApi.createConversation === "function") {
            window.ragApi.createConversation(initialTitle).catch(() => {});
        }

        return newConv;
    }

    /**
     * Add a message (user or ai) to a conversation.
     */
    addMessage(convId, role, text, sources = []) {
        let conv = this.conversations.find(c => c.id === convId);
        if (!conv) {
            conv = this.createConversation(convId, text.slice(0, 32) + "...");
        }

        // Auto-generate title from the first user question if still default
        if (role === "user" && (conv.title === "New Conversation" || !conv.title)) {
            conv.title = text.length > 36 ? text.slice(0, 36).trim() + "..." : text.trim();
            if (window.ragApi && typeof window.ragApi.renameConversation === "function") {
                window.ragApi.renameConversation(convId, conv.title).catch(() => {});
            }
        }

        const msg = {
            id: "msg_" + Date.now() + "_" + Math.random().toString(36).substr(2, 6),
            role,
            text,
            sources: Array.isArray(sources) ? sources : [],
            timestamp: Date.now()
        };

        conv.messages.push(msg);
        conv.updatedAt = Date.now();

        // Move active conversation to top of list
        this.conversations = [
            conv,
            ...this.conversations.filter(c => c.id !== convId)
        ];

        this.saveAll();
        return msg;
    }

    /**
     * Rename an existing conversation.
     */
    renameConversation(convId, newTitle) {
        const conv = this.conversations.find(c => c.id === convId);
        if (conv && newTitle && newTitle.trim()) {
            conv.title = newTitle.trim();
            conv.updatedAt = Date.now();
            this.saveAll();

            if (window.ragApi && typeof window.ragApi.renameConversation === "function") {
                window.ragApi.renameConversation(convId, conv.title).catch(() => {});
            }
            return true;
        }
        return false;
    }

    /**
     * Delete a conversation.
     */
    deleteConversation(convId) {
        this.conversations = this.conversations.filter(c => c.id !== convId);
        if (this.getActiveId() === convId) {
            const nextConv = this.conversations[0];
            this.setActiveId(nextConv ? nextConv.id : null);
        }
        this.saveAll();

        if (window.ragApi && typeof window.ragApi.deleteConversation === "function") {
            window.ragApi.deleteConversation(convId).catch(() => {});
        }
    }

    /**
     * Format a timestamp into human readable relative time.
     */
    static formatRelativeTime(timestamp) {
        if (!timestamp) return "";
        const diff = Math.floor((Date.now() - timestamp) / 1000);
        if (diff < 60) return "Just now";
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        if (diff < 172800) return "Yesterday";
        const date = new Date(timestamp);
        return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
}

window.conversationHistory = new ConversationHistory();
