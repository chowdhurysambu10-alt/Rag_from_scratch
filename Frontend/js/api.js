/**
 * RAG AI - Centralized Backend API Client
 * Connects directly to the existing FastAPI backend.
 */

const API_BASE = "http://127.0.0.1:8000";

const api = {
    /**
     * Check if the backend and vector DB are alive and accessible.
     * @returns {Promise<{healthy: boolean, vectorDb: string, collection: string, connected: boolean}>}
     */
    async checkHealth() {
        try {
            const res = await fetch(`${API_BASE}/`, { method: "GET" });
            if (!res.ok) return { healthy: false, vectorDb: "Qdrant Cloud", collection: "rag_documents_v2", connected: false };
            const data = await res.json();
            return {
                healthy: data.status === "active",
                vectorDb: data.database || "Qdrant Cloud",
                collection: data.collection || "rag_documents_v2",
                connected: data.connected !== false
            };
        } catch {
            return { healthy: false, vectorDb: "Qdrant Cloud", collection: "rag_documents_v2", connected: false };
        }
    },

    /**
     * Create a new RAG session on the backend.
     * @returns {Promise<{session_id: string}>}
     */
    async createSession() {
        const res = await fetch(`${API_BASE}/session`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });

        if (!res.ok) {
            const err = await res.text();
            throw new Error(`Failed to create session (${res.status}): ${err}`);
        }

        return await res.json();
    },

    /**
     * Send a question to the RAG chat endpoint.
     * @param {string} question
     * @param {string} sessionId
     * @param {string|null} [conversationId=null]
     * @returns {Promise<{answer: string, sources: Array, session_id: string, conversation_id: string}>}
     */
    async sendMessage(question, sessionId, conversationId = null) {
        if (!question || !question.trim()) {
            throw new Error("Question cannot be empty");
        }
        if (!sessionId && !conversationId) {
            throw new Error("Missing session ID");
        }

        const headers = window.authService ? window.authService.getAuthHeaders() : { "Content-Type": "application/json" };
        headers["Content-Type"] = "application/json";

        const res = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: headers,
            body: JSON.stringify({
                question: question.trim(),
                session_id: sessionId || conversationId,
                conversation_id: conversationId || sessionId
            })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || `Chat request failed with status ${res.status}`);
        }

        return data;
    },

    /**
     * Upload a document to Qdrant Cloud within a persistent session.
     * @param {File} file
     * @param {string|null} [sessionId=null]
     * @returns {Promise<{success: boolean, session_id: string, document_id: string, filename: string, chunks: number, pages: number}>}
     */
    async uploadDocument(file, sessionId = null) {
        if (!file) {
            throw new Error("No file provided");
        }

        const formData = new FormData();
        formData.append("file", file);
        if (sessionId) {
            formData.append("session_id", sessionId);
        }

        const headers = {};
        if (window.authService) {
            const token = window.authService.getToken();
            if (token) headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`${API_BASE}/api/upload`, {
            method: "POST",
            headers: headers,
            body: formData
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || `Upload failed with status ${res.status}`);
        }

        return data;
    },

    /**
     * Fetch all indexed documents and metrics from Qdrant Cloud.
     * @returns {Promise<{success: boolean, total_documents: number, total_chunks: number, collection: string, database: string, documents: Array}>}
     */
    async getDocuments() {
        const headers = window.authService ? window.authService.getAuthHeaders() : {};
        const res = await fetch(`${API_BASE}/api/documents`, {
            method: "GET",
            headers: headers
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `Failed to fetch documents (${res.status})`);
        }

        return await res.json();
    },

    /**
     * Delete a document and its embeddings by filename.
     * @param {string} filename
     * @returns {Promise<{success: boolean, filename: string, deleted_chunks: number, remaining_chunks: number}>}
     */
    async deleteDocument(filename) {
        const headers = window.authService ? window.authService.getAuthHeaders() : {};
        const res = await fetch(`${API_BASE}/api/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE",
            headers: headers
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.detail || `Failed to delete document (${res.status})`);
        }

        return data;
    },

    /**
     * Fetch private conversations belonging to the current user.
     */
    async getConversations() {
        const headers = window.authService ? window.authService.getAuthHeaders() : {};
        const res = await fetch(`${API_BASE}/api/conversations`, {
            method: "GET",
            headers: headers
        });
        if (!res.ok) return [];
        const data = await res.json();
        return data.conversations || [];
    },

    /**
     * Create a new conversation in Supabase for the current user.
     */
    async createConversation(title = "New Conversation") {
        const headers = window.authService ? window.authService.getAuthHeaders() : { "Content-Type": "application/json" };
        headers["Content-Type"] = "application/json";
        const res = await fetch(`${API_BASE}/api/conversations`, {
            method: "POST",
            headers: headers,
            body: JSON.stringify({ title })
        });
        if (!res.ok) throw new Error("Failed to create conversation");
        const data = await res.json();
        return data.conversation;
    },

    /**
     * Fetch messages for a conversation owned by the current user.
     */
    async getConversationMessages(conversationId) {
        const headers = window.authService ? window.authService.getAuthHeaders() : {};
        const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`, {
            method: "GET",
            headers: headers
        });
        if (!res.ok) return [];
        const data = await res.json();
        return data.messages || [];
    },

    /**
     * Rename a conversation.
     */
    async renameConversation(conversationId, title) {
        const headers = window.authService ? window.authService.getAuthHeaders() : { "Content-Type": "application/json" };
        headers["Content-Type"] = "application/json";
        const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
            method: "PATCH",
            headers: headers,
            body: JSON.stringify({ title })
        });
        return res.ok;
    },

    /**
     * Delete a conversation.
     */
    async deleteConversation(conversationId) {
        const headers = window.authService ? window.authService.getAuthHeaders() : {};
        const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
            method: "DELETE",
            headers: headers
        });
        return res.ok;
    }
};

// Export to window
window.ragApi = api;
