const API = "http://127.0.0.1:8000/api";

const totalDocsCount = document.getElementById("totalDocsCount");
const totalChunksCount = document.getElementById("totalChunksCount");
const searchInput = document.getElementById("searchInput");
const refreshBtn = document.getElementById("refreshBtn");
const documentsGrid = document.getElementById("documentsGrid");
const loadingState = document.getElementById("loadingState");
const errorState = document.getElementById("errorState");
const errorMessage = document.getElementById("errorMessage");
const emptyState = document.getElementById("emptyState");
const retryBtn = document.getElementById("retryBtn");
const toast = document.getElementById("toast");

let allDocuments = [];

// Toast notification helper
function showToast(message, isError = false) {
    toast.textContent = message;
    toast.className = `toast ${isError ? "error" : "success"}`;
    toast.hidden = false;

    clearTimeout(toast.timeoutId);
    toast.timeoutId = setTimeout(() => {
        toast.hidden = true;
    }, 3500);
}

// Fetch all documents from the backend
async function loadDocuments() {
    loadingState.hidden = false;
    errorState.hidden = true;
    emptyState.hidden = true;
    documentsGrid.hidden = true;

    try {
        const response = await fetch(`${API}/documents`);
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        allDocuments = data.documents || [];

        totalDocsCount.textContent = data.total_documents.toLocaleString();
        totalChunksCount.textContent = data.total_chunks.toLocaleString();

        loadingState.hidden = true;

        if (allDocuments.length === 0) {
            emptyState.hidden = false;
            documentsGrid.hidden = true;
        } else {
            emptyState.hidden = true;
            documentsGrid.hidden = false;
            renderDocuments(allDocuments);
        }
    } catch (err) {
        console.error("Error fetching documents:", err);
        loadingState.hidden = true;
        errorMessage.textContent = `Could not load documents: ${err.message}. Ensure the backend server is running on port 8000.`;
        errorState.hidden = false;
    }
}

// Render document cards into the grid
function renderDocuments(docs) {
    documentsGrid.innerHTML = "";

    if (docs.length === 0) {
        documentsGrid.innerHTML = `
            <div class="no-results">
                <p>No documents matching your search.</p>
            </div>
        `;
        return;
    }

    docs.forEach((doc) => {
        const card = document.createElement("div");
        card.className = "doc-card";
        card.dataset.filename = doc.filename;

        // File badge color / icon by type
        let iconText = doc.type || "DOC";
        let iconClass = "file-icon-pdf";
        if (iconText === "TXT") iconClass = "file-icon-txt";
        else if (iconText === "DOCX" || iconText === "DOC") iconClass = "file-icon-docx";
        else if (iconText === "CSV") iconClass = "file-icon-csv";

        card.innerHTML = `
            <div class="doc-card-header">
                <div class="file-icon-badge ${iconClass}">${escapeHtml(iconText)}</div>
                <div class="doc-title-wrapper" title="${escapeHtml(doc.filename)}">
                    <h4 class="doc-filename">${escapeHtml(doc.filename)}</h4>
                    <span class="doc-source-path">${escapeHtml(doc.source)}</span>
                </div>
            </div>

            <div class="doc-card-body">
                <div class="doc-meta-pills">
                    <span class="meta-pill chunks-pill">
                        <strong>${doc.chunks.toLocaleString()}</strong> chunks
                    </span>
                    <span class="meta-pill pages-pill">
                        <strong>${doc.pages}</strong> ${doc.pages === 1 ? "page" : "pages"}
                    </span>
                </div>
            </div>

            <div class="doc-card-footer">
                <button class="delete-doc-btn" data-filename="${escapeHtml(doc.filename)}" title="Remove document and all chunks from vector database">
                    <span class="trash-icon">🗑️</span> Delete
                </button>
            </div>
        `;

        const deleteBtn = card.querySelector(".delete-doc-btn");
        deleteBtn.addEventListener("click", () => handleDelete(doc.filename, doc.chunks, card, deleteBtn));

        documentsGrid.appendChild(card);
    });
}

// Handle document deletion
async function handleDelete(filename, chunks, cardElement, buttonElement) {
    const confirmed = window.confirm(
        `Are you sure you want to delete "${filename}" (${chunks} chunks) from ChromaDB?\n\nThis will permanently remove its vector embeddings.`
    );

    if (!confirmed) return;

    buttonElement.disabled = true;
    buttonElement.innerHTML = `<span class="spinner-small"></span> Deleting...`;

    try {
        const response = await fetch(`${API}/documents/${encodeURIComponent(filename)}`, {
            method: "DELETE"
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `Server returned ${response.status}`);
        }

        const data = await response.json();

        // Animate card removal
        cardElement.classList.add("deleting");
        setTimeout(() => {
            cardElement.remove();

            // Update local memory list
            allDocuments = allDocuments.filter(d => d.filename !== filename);
            const newTotalChunks = allDocuments.reduce((sum, d) => sum + d.chunks, 0);

            totalDocsCount.textContent = allDocuments.length.toLocaleString();
            totalChunksCount.textContent = newTotalChunks.toLocaleString();

            showToast(`Deleted "${filename}" (${data.deleted_chunks} chunks removed)`);

            if (allDocuments.length === 0) {
                emptyState.hidden = false;
                documentsGrid.hidden = true;
            }
        }, 300);

    } catch (err) {
        console.error("Failed to delete document:", err);
        buttonElement.disabled = false;
        buttonElement.innerHTML = `<span class="trash-icon">🗑️</span> Delete`;
        showToast(`Failed to delete document: ${err.message}`, true);
    }
}

// Search filtering
searchInput.addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
        renderDocuments(allDocuments);
        return;
    }

    const filtered = allDocuments.filter(doc =>
        doc.filename.toLowerCase().includes(query) ||
        doc.source.toLowerCase().includes(query)
    );
    renderDocuments(filtered);
});

// Refresh button
refreshBtn.addEventListener("click", loadDocuments);
retryBtn.addEventListener("click", loadDocuments);

// Utility to escape HTML
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Initial fetch on page load
loadDocuments();
