/**
 * RAG AI - Centralized Backend API Client
 * Connects directly to the existing FastAPI backend.
 */

const API_BASE = "http://127.0.0.1:8000";

const api = {
    /**
     * Check if the backend is alive and accessible.
     */
    async checkHealth() {
        try {
            const res = await fetch(`${API_BASE}/`, { method: "GET" });
            if (!res.ok) return false;
            const data = await res.json();
            return data.status === "active";
        } catch {
            return false;
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
     * @returns {Promise<{answer: string, sources: Array, session_id: string}>}
     */
    async sendMessage(question, sessionId) {
        if (!question || !question.trim()) {
            throw new Error("Question cannot be empty");
        }
        if (!sessionId) {
            throw new Error("Missing session ID");
        }

        const res = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question.trim(),
                session_id: sessionId
            })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || `Chat request failed with status ${res.status}`);
        }

        return data;
    },

    /**
     * Upload a document to ChromaDB within a persistent session.
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

        const res = await fetch(`${API_BASE}/api/upload`, {
            method: "POST",
            body: formData
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || `Upload failed with status ${res.status}`);
        }

        return data;
    },

    /**
     * Fetch all indexed documents and metrics from ChromaDB.
     * @returns {Promise<{success: boolean, total_documents: number, total_chunks: number, documents: Array}>}
     */
    async getDocuments() {
        const res = await fetch(`${API_BASE}/api/documents`, {
            method: "GET"
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
        const res = await fetch(`${API_BASE}/api/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE"
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.detail || `Failed to delete document (${res.status})`);
        }

        return data;
    }
};

// Export to window
window.ragApi = api;
