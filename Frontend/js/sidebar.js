/**
 * RAG AI - Shared Sidebar & Navigation Controller
 * Manages responsive sidebar drawer, conversation history rendering,
 * and workspace status across all pages.
 */

document.addEventListener("DOMContentLoaded", () => {
    initSidebar();
});

function initSidebar() {
    const sidebar = document.querySelector(".sidebar");
    const backdrop = document.querySelector(".sidebar-backdrop");
    const menuToggleBtn = document.querySelector(".menu-toggle-btn");
    const sidebarCloseBtn = document.querySelector(".sidebar-close-btn");
    const newChatBtn = document.querySelector(".new-chat-btn");
    const historyList = document.querySelector(".history-list");
    const historyBadge = document.querySelector(".history-badge");

    // 1. Mobile Drawer Toggle
    if (menuToggleBtn && sidebar && backdrop) {
        menuToggleBtn.addEventListener("click", () => {
            sidebar.classList.add("open");
            backdrop.classList.add("active");
        });
    }

    const closeSidebar = () => {
        if (sidebar) sidebar.classList.remove("open");
        if (backdrop) backdrop.classList.remove("active");
    };

    if (sidebarCloseBtn) sidebarCloseBtn.addEventListener("click", closeSidebar);
    if (backdrop) backdrop.addEventListener("click", closeSidebar);

    // 2. "New Chat" Button Handler
    if (newChatBtn) {
        newChatBtn.addEventListener("click", async () => {
            const isChatPage = window.location.pathname.endsWith("index.html") || 
                               window.location.pathname.endsWith("/Frontend/") || 
                               window.location.pathname.endsWith("/Frontend");

            if (isChatPage && typeof window.startNewConversation === "function") {
                await window.startNewConversation();
            } else {
                try {
                    newChatBtn.disabled = true;
                    newChatBtn.textContent = "Starting...";
                    const session = await window.ragApi.createSession();
                    window.conversationHistory.createConversation(session.session_id);
                    window.location.href = "index.html";
                } catch (e) {
                    console.error("Failed to start new chat:", e);
                    window.location.href = "index.html";
                }
            }
        });
    }

    // 3. Render Conversation History List
    renderSidebarHistory();

    // 4. Live Backend Health Check
    checkBackendStatus();
}

/**
 * Render all saved conversations into the sidebar list.
 */
function renderSidebarHistory() {
    const historyList = document.querySelector(".history-list");
    const historyBadge = document.querySelector(".history-badge");
    if (!historyList) return;

    const conversations = window.conversationHistory.loadAll();
    const activeId = window.conversationHistory.getActiveId();

    if (historyBadge) {
        historyBadge.textContent = conversations.length;
    }

    historyList.innerHTML = "";

    if (conversations.length === 0) {
        historyList.innerHTML = `
            <li class="history-empty">
                No recent conversations.<br>Click "+ New Chat" to begin.
            </li>
        `;
        return;
    }

    conversations.forEach((conv) => {
        const item = document.createElement("li");
        item.className = `history-item ${conv.id === activeId ? "active" : ""}`;
        item.dataset.id = conv.id;

        const timeStr = ConversationHistory.formatRelativeTime(conv.updatedAt);

        item.innerHTML = `
            <div class="history-content">
                <span class="history-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</span>
                <span class="history-meta">${timeStr}</span>
            </div>
            <div class="history-actions">
                <button class="history-action-btn rename" title="Rename conversation" aria-label="Rename">
                    ✎
                </button>
                <button class="history-action-btn delete" title="Delete conversation" aria-label="Delete">
                    ✕
                </button>
            </div>
        `;

        // Switch to this conversation
        item.addEventListener("click", (e) => {
            if (e.target.closest(".history-actions")) return;
            selectConversation(conv.id);
        });

        // Rename conversation
        const renameBtn = item.querySelector(".rename");
        renameBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            promptRenameConversation(conv.id, conv.title);
        });

        // Delete conversation
        const deleteBtn = item.querySelector(".delete");
        deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            promptDeleteConversation(conv.id, conv.title);
        });

        historyList.appendChild(item);
    });
}

/**
 * Handle conversation selection.
 */
function selectConversation(convId) {
    window.conversationHistory.setActiveId(convId);

    const isChatPage = window.location.pathname.endsWith("index.html") || 
                       window.location.pathname.endsWith("/Frontend/") || 
                       window.location.pathname.endsWith("/Frontend");

    if (isChatPage && typeof window.loadConversation === "function") {
        window.loadConversation(convId);
        renderSidebarHistory();
    } else {
        window.location.href = "index.html";
    }
}

/**
 * Prompt to rename a conversation using modal or browser prompt.
 */
function promptRenameConversation(convId, currentTitle) {
    const newTitle = window.prompt("Enter new conversation title:", currentTitle);
    if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
        window.conversationHistory.renameConversation(convId, newTitle.trim());
        renderSidebarHistory();
        if (typeof window.updateConversationTitleDisplay === "function") {
            window.updateConversationTitleDisplay(newTitle.trim());
        }
    }
}

/**
 * Prompt to delete a conversation with confirmation.
 */
function promptDeleteConversation(convId, title) {
    const confirmed = window.confirm(`Delete conversation "${title}"?\n\nThis will remove it from your chat history.`);
    if (confirmed) {
        window.conversationHistory.deleteConversation(convId);
        renderSidebarHistory();

        const isChatPage = window.location.pathname.endsWith("index.html") || 
                           window.location.pathname.endsWith("/Frontend/") || 
                           window.location.pathname.endsWith("/Frontend");

        if (isChatPage && typeof window.onActiveConversationDeleted === "function") {
            window.onActiveConversationDeleted(convId);
        }
    }
}

/**
 * Ping backend periodically to show connected status dot and vector database.
 */
async function checkBackendStatus() {
    const statusDot = document.querySelector(".status-dot");
    const statusText = document.querySelector(".status-pill span");
    const collectionBadge = document.querySelector(".collection-badge");

    const updateStatus = (health) => {
        if (!statusDot || !statusText) return;
        const isHealthy = health && health.healthy;
        const isConnected = health && health.connected;
        const dbName = (health && health.vectorDb) || "Qdrant Cloud";
        const collName = (health && health.collection) || "rag_documents_v2";

        if (isHealthy && isConnected) {
            statusDot.style.backgroundColor = "var(--success)";
            statusDot.style.boxShadow = "0 0 8px rgba(16, 185, 129, 0.6)";
            statusText.textContent = `${dbName} (Connected)`;
        } else if (isHealthy) {
            statusDot.style.backgroundColor = "var(--warning, #f59e0b)";
            statusDot.style.boxShadow = "0 0 8px rgba(245, 158, 11, 0.6)";
            statusText.textContent = `${dbName} (Connecting...)`;
        } else {
            statusDot.style.backgroundColor = "var(--danger)";
            statusDot.style.boxShadow = "0 0 8px rgba(239, 68, 68, 0.6)";
            statusText.textContent = "Backend Offline (Port 8000)";
        }

        if (collectionBadge && collName) {
            collectionBadge.textContent = `Collection: ${collName}`;
        }
    };

    const initialHealth = await window.ragApi.checkHealth();
    updateStatus(initialHealth);

    // Poll every 30 seconds
    setInterval(async () => {
        const currentHealth = await window.ragApi.checkHealth();
        updateStatus(currentHealth);
    }, 30000);
}

// Utility HTML escape
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

window.renderSidebarHistory = renderSidebarHistory;
