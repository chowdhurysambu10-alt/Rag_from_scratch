/**
 * RAG AI - Conversation History Manager
 * Manages persistent conversation sessions using browser LocalStorage.
 * Aligns each conversation with a backend session_id.
 */

const STORAGE_KEY_CONVERSATIONS = "rag_ai_conversations_v2";
const STORAGE_KEY_ACTIVE_ID = "rag_ai_active_conv_id";

class ConversationHistory {
    constructor() {
        this.conversations = this.loadAll();
    }

    /**
     * Load all saved conversations from localStorage.
     */
    loadAll() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY_CONVERSATIONS);
            if (!raw) return [];
            const list = JSON.parse(raw);
            return Array.isArray(list) ? list : [];
        } catch (e) {
            console.error("Failed to parse conversations from storage:", e);
            return [];
        }
    }

    /**
     * Save current conversation list to localStorage.
     */
    saveAll() {
        try {
            localStorage.setItem(STORAGE_KEY_CONVERSATIONS, JSON.stringify(this.conversations));
        } catch (e) {
            console.error("Failed to save conversations to storage:", e);
        }
    }

    /**
     * Get the active conversation ID.
     */
    getActiveId() {
        return localStorage.getItem(STORAGE_KEY_ACTIVE_ID) || null;
    }

    /**
     * Ensure an active conversation and persistent session ID exist in localStorage.
     */
    async ensureActiveSessionId() {
        let activeId = this.getActiveId();
        let conv = activeId ? this.conversations.find(c => c.id === activeId) : null;
        if (!activeId || !conv) {
            try {
                if (window.ragApi && typeof window.ragApi.createSession === "function") {
                    const res = await window.ragApi.createSession();
                    activeId = res.session_id;
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
            localStorage.setItem(STORAGE_KEY_ACTIVE_ID, id);
        } else {
            localStorage.removeItem(STORAGE_KEY_ACTIVE_ID);
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
     * @param {string} sessionId
     * @param {string} [initialTitle="New Conversation"]
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
