/**
 * RAG AI - Document Upload & Processing Pipeline Controller
 * Manages drag-and-drop, client-side validation, 5-stage workflow stepper,
 * and direct backend ingestion into Qdrant Cloud.
 */

document.addEventListener("DOMContentLoaded", () => {
    initUpload();
});

let selectedFile = null;
let isProcessing = false;

function initUpload() {
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const browseBtn = document.getElementById("browseBtn");
    const selectedFileCard = document.getElementById("selectedFileCard");
    const fileNameDisplay = document.getElementById("fileNameDisplay");
    const fileSizeDisplay = document.getElementById("fileSizeDisplay");
    const removeFileBtn = document.getElementById("removeFileBtn");
    const uploadActionBtn = document.getElementById("uploadActionBtn");
    const workflowSection = document.getElementById("workflowSection");
    const uploadSuccessCard = document.getElementById("uploadSuccessCard");
    const uploadErrorCard = document.getElementById("uploadErrorCard");
    const errorMessageText = document.getElementById("errorMessageText");

    // 1. Browse Files Click
    if (browseBtn && fileInput) {
        browseBtn.addEventListener("click", () => fileInput.click());
    }

    if (fileInput) {
        fileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) handleFileSelected(file);
        });
    }

    // 2. Drag & Drop Handlers
    if (dropzone) {
        ["dragenter", "dragover"].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                dropzone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach(name => {
            dropzone.addEventListener(name, (e) => {
                e.preventDefault();
                dropzone.classList.remove("drag-over");
            });
        });

        dropzone.addEventListener("drop", (e) => {
            const files = e.dataTransfer.files;
            if (files && files.length > 0) {
                handleFileSelected(files[0]);
            }
        });
    }

    // 3. Remove Selected File
    if (removeFileBtn) {
        removeFileBtn.addEventListener("click", resetFileSelection);
    }

    // 4. Upload & Process Submission
    if (uploadActionBtn) {
        uploadActionBtn.addEventListener("click", handleUploadSubmit);
    }
}

/**
 * Validate and prepare selected file.
 */
function handleFileSelected(file) {
    const uploadErrorCard = document.getElementById("uploadErrorCard");
    const errorMessageText = document.getElementById("errorMessageText");
    const selectedFileCard = document.getElementById("selectedFileCard");
    const fileNameDisplay = document.getElementById("fileNameDisplay");
    const fileSizeDisplay = document.getElementById("fileSizeDisplay");
    const uploadActionBtn = document.getElementById("uploadActionBtn");
    const uploadSuccessCard = document.getElementById("uploadSuccessCard");

    if (uploadErrorCard) uploadErrorCard.hidden = true;
    if (uploadSuccessCard) uploadSuccessCard.hidden = true;

    // Check PDF extension and MIME
    const isPdf = file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf";
    if (!isPdf) {
        showError("Invalid format: Only PDF documents are supported.");
        return;
    }

    // Check size limit: 20MB
    const maxBytes = 20 * 1024 * 1024;
    if (file.size > maxBytes) {
        showError("File too large: Maximum supported PDF size is 20 MB.");
        return;
    }

    if (file.size === 0) {
        showError("The selected PDF is empty (0 bytes).");
        return;
    }

    selectedFile = file;

    // Populate display
    if (fileNameDisplay) fileNameDisplay.textContent = file.name;
    if (fileSizeDisplay) fileSizeDisplay.textContent = formatBytes(file.size);
    if (selectedFileCard) selectedFileCard.hidden = false;
    if (uploadActionBtn) uploadActionBtn.disabled = false;
}

/**
 * Handle document upload and workflow stage animation.
 */
async function handleUploadSubmit() {
    if (!selectedFile || isProcessing) return;

    const uploadActionBtn = document.getElementById("uploadActionBtn");
    const workflowSection = document.getElementById("workflowSection");
    const uploadSuccessCard = document.getElementById("uploadSuccessCard");
    const uploadErrorCard = document.getElementById("uploadErrorCard");
    const removeFileBtn = document.getElementById("removeFileBtn");

    isProcessing = true;
    if (uploadActionBtn) {
        uploadActionBtn.disabled = true;
        uploadActionBtn.innerHTML = `<span>⏳</span> Processing Document...`;
    }
    if (removeFileBtn) removeFileBtn.disabled = true;
    if (uploadErrorCard) uploadErrorCard.hidden = true;
    if (uploadSuccessCard) uploadSuccessCard.hidden = true;

    // Show workflow stepper
    if (workflowSection) workflowSection.hidden = false;
    resetStepper();

    // Stage 1: Uploading
    setStepStatus(1, "in-progress", "Uploading file to server...");

    try {
        // Create an active progress transition while the network call completes
        const stageTimer = setTimeout(() => {
            setStepStatus(1, "completed", "File uploaded successfully");
            setStepStatus(2, "in-progress", "Extracting text from PDF pages...");
        }, 600);

        const stageTimer2 = setTimeout(() => {
            setStepStatus(2, "completed", "Text extraction complete");
            setStepStatus(3, "in-progress", "Splitting into semantic chunks...");
        }, 1300);

        const stageTimer3 = setTimeout(() => {
            setStepStatus(3, "completed", "Chunks created");
            setStepStatus(4, "in-progress", "Generating neural embeddings...");
        }, 2000);

        // 1. Get or create persistent conversation session ID
        let activeSessionId = null;
        if (window.conversationHistory && typeof window.conversationHistory.ensureActiveSessionId === "function") {
            activeSessionId = await window.conversationHistory.ensureActiveSessionId();
        } else {
            activeSessionId = localStorage.getItem("rag_ai_active_conv_id") || localStorage.getItem("session_id");
        }

        // Actual backend API call passing persistent session ID
        const response = await window.ragApi.uploadDocument(selectedFile, activeSessionId);

        clearTimeout(stageTimer);
        clearTimeout(stageTimer2);
        clearTimeout(stageTimer3);

        // Mark all steps completed on backend confirmation
        setStepStatus(1, "completed", "File uploaded");
        setStepStatus(2, "completed", "Text extracted");
        setStepStatus(3, "completed", `${response.chunks} chunks generated`);
        setStepStatus(4, "completed", "MiniLM embeddings generated");
        setStepStatus(5, "completed", `Stored in Qdrant Cloud (${response.collection_name || "rag_documents_v2"})`);

        // Show Success Result Card
        showSuccess(response);

        // Store persistent session ID in localStorage and update conversation metadata
        const sid = response.session_id || activeSessionId;
        if (sid) {
            localStorage.setItem("session_id", sid);
            localStorage.setItem("rag_ai_active_conv_id", sid);
            if (window.conversationHistory) {
                window.conversationHistory.setActiveId(sid);
                const conv = window.conversationHistory.getActiveConversation();
                if (conv && (conv.title === "New Conversation" || !conv.title)) {
                    window.conversationHistory.renameConversation(sid, `Doc: ${response.filename}`);
                }
                if (typeof window.renderSidebarHistory === "function") {
                    window.renderSidebarHistory();
                }
            }
        }

    } catch (err) {
        console.error("Upload failed:", err);
        markCurrentStepError(err.message);
        showError(err.message);
    } finally {
        isProcessing = false;
        if (uploadActionBtn) {
            uploadActionBtn.disabled = false;
            uploadActionBtn.innerHTML = `<span>Upload Document →</span>`;
        }
        if (removeFileBtn) removeFileBtn.disabled = false;
    }
}

/**
 * Set status for a stepper step (1 to 5).
 * @param {number} stepNum
 * @param {"waiting"|"in-progress"|"completed"|"error"} status
 * @param {string} badgeText
 */
function setStepStatus(stepNum, status, badgeText) {
    const item = document.getElementById(`stepItem${stepNum}`);
    if (!item) return;

    item.className = `stepper-item ${status}`;
    const badge = item.querySelector(".step-status-badge");
    const node = item.querySelector(".step-node");

    if (badge) badge.textContent = badgeText;
    if (node) {
        if (status === "completed") {
            node.innerHTML = "✓";
        } else if (status === "error") {
            node.innerHTML = "✕";
        } else if (status === "in-progress") {
            node.innerHTML = "●";
        } else {
            node.innerHTML = String(stepNum);
        }
    }
}

/**
 * Reset all stepper stages to waiting.
 */
function resetStepper() {
    const steps = [
        { num: 1, text: "Waiting" },
        { num: 2, text: "Waiting" },
        { num: 3, text: "Waiting" },
        { num: 4, text: "Waiting" },
        { num: 5, text: "Waiting" },
    ];

    steps.forEach(s => {
        setStepStatus(s.num, "waiting", s.text);
    });
}

function markCurrentStepError(errorMsg) {
    // Find active step or default to current
    for (let i = 1; i <= 5; i++) {
        const item = document.getElementById(`stepItem${i}`);
        if (item && item.classList.contains("in-progress")) {
            setStepStatus(i, "error", "Failed");
            return;
        }
    }
    setStepStatus(1, "error", "Upload error");
}

/**
 * Show the success card.
 */
function showSuccess(data) {
    const uploadSuccessCard = document.getElementById("uploadSuccessCard");
    const successTitle = document.getElementById("successTitle");
    const successDetails = document.getElementById("successDetails");
    const chatDocBtn = document.getElementById("chatDocBtn");

    if (!uploadSuccessCard) return;

    if (successTitle) {
        successTitle.textContent = `"${data.filename}" is Ready!`;
    }
    if (successDetails) {
        successDetails.textContent = `Successfully extracted and indexed ${data.chunks} chunks into Qdrant Cloud collection "${data.collection_name || "rag_documents_v2"}".`;
    }
    if (chatDocBtn) {
        chatDocBtn.onclick = () => {
            window.location.href = "index.html";
        };
    }

    uploadSuccessCard.hidden = false;
}

/**
 * Show error card.
 */
function showError(message) {
    const uploadErrorCard = document.getElementById("uploadErrorCard");
    const errorMessageText = document.getElementById("errorMessageText");

    if (errorMessageText) errorMessageText.textContent = message;
    if (uploadErrorCard) uploadErrorCard.hidden = false;
}

/**
 * Reset selected file state.
 */
function resetFileSelection() {
    selectedFile = null;
    const fileInput = document.getElementById("fileInput");
    const selectedFileCard = document.getElementById("selectedFileCard");
    const uploadActionBtn = document.getElementById("uploadActionBtn");
    const workflowSection = document.getElementById("workflowSection");
    const uploadSuccessCard = document.getElementById("uploadSuccessCard");
    const uploadErrorCard = document.getElementById("uploadErrorCard");

    if (fileInput) fileInput.value = "";
    if (selectedFileCard) selectedFileCard.hidden = true;
    if (uploadActionBtn) uploadActionBtn.disabled = true;
    if (workflowSection) workflowSection.hidden = true;
    if (uploadSuccessCard) uploadSuccessCard.hidden = true;
    if (uploadErrorCard) uploadErrorCard.hidden = true;
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}
