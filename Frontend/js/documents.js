/**
 * RAG AI - Knowledge Base Documents Manager
 * Handles document metrics, search & filtering, skeleton states,
 * deletion modal confirmation, and direct Qdrant Cloud management.
 */

document.addEventListener("DOMContentLoaded", () => {
    initDocumentsPage();
});

let allDocuments = [];
let pendingDeleteDoc = null;

function initDocumentsPage() {
    const searchInput = document.getElementById("searchFieldInput");
    const refreshBtn = document.getElementById("refreshDocsBtn");
    const filterPills = document.querySelectorAll(".filter-pill");

    // Modal elements
    const deleteModal = document.getElementById("deleteModal");
    const cancelDeleteBtn = document.getElementById("cancelDeleteBtn");
    const confirmDeleteBtn = document.getElementById("confirmDeleteBtn");
    const modalCloseBtn = document.getElementById("modalCloseBtn");

    // 1. Initial Load
    fetchDocuments();

    // 2. Real-time Search
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            filterAndRender();
        });
    }

    // 3. Filter Pills
    filterPills.forEach(pill => {
        pill.addEventListener("click", () => {
            filterPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            filterAndRender();
        });
    });

    // 4. Refresh Button
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            refreshBtn.classList.add("spinning");
            fetchDocuments().finally(() => {
                setTimeout(() => refreshBtn.classList.remove("spinning"), 600);
            });
        });
    }

    // 5. Delete Modal Handlers
    const closeModal = () => {
        if (deleteModal) deleteModal.classList.remove("active");
        pendingDeleteDoc = null;
    };

    if (cancelDeleteBtn) cancelDeleteBtn.addEventListener("click", closeModal);
    if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeModal);
    if (confirmDeleteBtn) confirmDeleteBtn.addEventListener("click", executeDocumentDeletion);
}

/**
 * Fetch document list and statistics from the FastAPI backend.
 */
async function fetchDocuments() {
    const docsGrid = document.getElementById("docsGrid");
    const skeletonWrap = document.getElementById("skeletonWrap");
    const emptyState = document.getElementById("emptyState");
    const errorState = document.getElementById("errorState");

    if (skeletonWrap) skeletonWrap.hidden = false;
    if (docsGrid) docsGrid.hidden = true;
    if (emptyState) emptyState.hidden = true;
    if (errorState) errorState.hidden = true;

    try {
        const data = await window.ragApi.getDocuments();
        allDocuments = data.documents || [];

        // Update statistics cards
        updateMetricCards(data.total_documents, data.total_chunks, data.collection);

        if (skeletonWrap) skeletonWrap.hidden = true;

        if (allDocuments.length === 0) {
            if (emptyState) emptyState.hidden = false;
        } else {
            if (docsGrid) docsGrid.hidden = false;
            filterAndRender();
        }
    } catch (err) {
        console.error("Error fetching documents:", err);
        if (skeletonWrap) skeletonWrap.hidden = true;
        if (errorState) {
            const errText = document.getElementById("errorMessageText");
            if (errText) errText.textContent = err.message;
            errorState.hidden = false;
        }
    }
}

/**
 * Update Metric / Statistics Overview Cards.
 */
function updateMetricCards(totalDocs, totalChunks, collection) {
    const totalDocsVal = document.getElementById("totalDocsVal");
    const totalChunksVal = document.getElementById("totalChunksVal");
    const collectionVal = document.getElementById("collectionVal");

    if (totalDocsVal) totalDocsVal.textContent = (totalDocs !== undefined && totalDocs !== null ? totalDocs : 0).toLocaleString();
    if (totalChunksVal) totalChunksVal.textContent = (totalChunks !== undefined && totalChunks !== null ? totalChunks : 0).toLocaleString();
    if (collectionVal && collection) collectionVal.textContent = collection;
}

/**
 * Filter documents according to search query and active category pill.
 */
function filterAndRender() {
    const searchInput = document.getElementById("searchFieldInput");
    const activeFilter = document.querySelector(".filter-pill.active")?.dataset.filter || "all";
    const query = (searchInput?.value || "").toLowerCase().trim();

    let filtered = allDocuments.filter(doc => {
        const matchesQuery = !query || 
            doc.filename.toLowerCase().includes(query) || 
            doc.source.toLowerCase().includes(query);

        if (!matchesQuery) return false;

        if (activeFilter === "all") return true;
        if (activeFilter === "pdf") return doc.type === "PDF";
        if (activeFilter === "other") return doc.type !== "PDF";
        return true;
    });

    renderDocumentCards(filtered);
}

/**
 * Render document cards into the grid.
 */
function renderDocumentCards(docs) {
    const docsGrid = document.getElementById("docsGrid");
    if (!docsGrid) return;

    docsGrid.innerHTML = "";

    if (docs.length === 0) {
        docsGrid.innerHTML = `
            <div class="state-panel" style="grid-column: 1 / -1;">
                <div class="state-icon">🔍</div>
                <h3 class="state-title">No matching documents found</h3>
                <p class="state-desc">Try searching for a different keyword or switch your filter.</p>
            </div>
        `;
        return;
    }

    docs.forEach(doc => {
        const card = document.createElement("div");
        card.className = "document-card";
        card.dataset.filename = doc.filename;

        const typeClass = (doc.type || "DOC").toLowerCase();

        card.innerHTML = `
            <div class="doc-header-wrap">
                <div class="doc-badge-icon ${typeClass}">${escapeHtml(doc.type || "DOC")}</div>
                <div class="doc-title-box">
                    <h4 class="doc-name-h4" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</h4>
                    <span class="doc-path-sub" title="${escapeHtml(doc.source)}">${escapeHtml(doc.source)}</span>
                </div>
            </div>

            <div class="doc-body-pills">
                <span class="doc-pill chunks">
                    <strong>${doc.chunks.toLocaleString()}</strong> chunks
                </span>
                <span class="doc-pill pages">
                    <strong>${doc.pages}</strong> ${doc.pages === 1 ? "page" : "pages"}
                </span>
                <span class="doc-pill status-ready">
                    <span class="status-tiny-dot"></span> ${escapeHtml(doc.status || "Indexed")}
                </span>
                <span class="doc-pill uploader-pill" title="Uploaded by ${escapeHtml(doc.uploaded_by || "Shared Library")}">
                    👤 ${escapeHtml(doc.uploaded_by || "Shared Library")}
                </span>
            </div>

            <div class="doc-footer-wrap">
                <button class="doc-action-btn doc-chat-btn" title="Chat with this document">
                    <span>💬</span> Chat
                </button>
                <button class="doc-action-btn doc-delete-btn" title="Delete from vector store">
                    <span>🗑️</span> Delete
                </button>
            </div>
        `;

        // Chat with doc button
        const chatBtn = card.querySelector(".doc-chat-btn");
        chatBtn.addEventListener("click", () => {
            window.location.href = "index.html";
        });

        // Delete button
        const deleteBtn = card.querySelector(".doc-delete-btn");
        deleteBtn.addEventListener("click", () => {
            openDeleteModal(doc);
        });

        docsGrid.appendChild(card);
    });
}

/**
 * Open the deletion confirmation modal.
 * Enforces admin or uploader authorization for shared documents.
 */
function openDeleteModal(doc) {
    const user = window.authService ? window.authService.getUser() : null;
    const isAdmin = user && (user.role === "admin" || (user.email && user.email.toLowerCase().includes("admin")));
    const isUploader = user && doc.uploaded_by && user.email === doc.uploaded_by;

    // In multi-user mode, restrict deletion if user is not admin or uploader
    if (user && !user.isGuest && !isAdmin && !isUploader) {
        showToast("Administrator authorization required to delete shared Knowledge Base documents.", "error");
        return;
    }

    pendingDeleteDoc = doc;
    const deleteModal = document.getElementById("deleteModal");
    const modalFilenameDisplay = document.getElementById("modalFilenameDisplay");
    const modalChunksDisplay = document.getElementById("modalChunksDisplay");

    if (modalFilenameDisplay) modalFilenameDisplay.textContent = doc.filename;
    if (modalChunksDisplay) modalChunksDisplay.textContent = `${doc.chunks} vector chunks`;

    if (deleteModal) deleteModal.classList.add("active");
}

/**
 * Execute document deletion.
 */
async function executeDocumentDeletion() {
    if (!pendingDeleteDoc) return;

    const confirmDeleteBtn = document.getElementById("confirmDeleteBtn");
    const deleteModal = document.getElementById("deleteModal");
    const filename = pendingDeleteDoc.filename;

    if (confirmDeleteBtn) {
        confirmDeleteBtn.disabled = true;
        confirmDeleteBtn.textContent = "Deleting...";
    }

    try {
        const result = await window.ragApi.deleteDocument(filename);

        // Find and animate card
        const card = document.querySelector(`.document-card[data-filename="${CSS.escape(filename)}"]`);
        if (card) {
            card.classList.add("deleting");
            setTimeout(() => card.remove(), 300);
        }

        // Update list
        allDocuments = allDocuments.filter(d => d.filename !== filename);
        const newTotalChunks = result.remaining_chunks !== undefined ? result.remaining_chunks : allDocuments.reduce((sum, d) => sum + d.chunks, 0);
        updateMetricCards(allDocuments.length, newTotalChunks);

        showToast(`"${filename}" deleted (${result.deleted_chunks} chunks removed)`, "success");

        if (allDocuments.length === 0) {
            const emptyState = document.getElementById("emptyState");
            const docsGrid = document.getElementById("docsGrid");
            if (emptyState) emptyState.hidden = false;
            if (docsGrid) docsGrid.hidden = true;
        }

    } catch (err) {
        console.error("Deletion error:", err);
        showToast(`Failed to delete document: ${err.message}`, "error");
    } finally {
        if (confirmDeleteBtn) {
            confirmDeleteBtn.disabled = false;
            confirmDeleteBtn.textContent = "Delete Document";
        }
        if (deleteModal) deleteModal.classList.remove("active");
        pendingDeleteDoc = null;
    }
}

/**
 * Floating toast notification helper.
 */
function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === "success" ? "✓" : "⚠️"}</span>
        <span>${escapeHtml(message)}</span>
    `;

    let container = document.querySelector(".toast-container");
    if (!container) {
        container = document.createElement("div");
        container.className = "toast-container";
        document.body.appendChild(container);
    }

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(12px)";
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
