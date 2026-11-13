


const fileInput = document.getElementById("fileInput");
const browseBtn = document.getElementById("browseBtn");
const dropZone = document.getElementById("dropZone");

const fileCard = document.getElementById("fileCard");
const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");



const removeBtn = document.getElementById("removeBtn");

const uploadBtn = document.getElementById("uploadBtn");

const statusMessage = document.getElementById("statusMessage");

let selectedFile = null;

// Open file picker
browseBtn.addEventListener("click", () => {
    fileInput.click();
});

// Select file
fileInput.addEventListener("change", (event) => {
    handleFile(event.target.files[0]);
});

// Validate and display file
function handleFile(file) {

    if (!file) return;

    const isPDF =
        file.type === "application/pdf" &&
        file.name.toLowerCase().endsWith(".pdf");

    if (!isPDF) {
        showStatus("Please select a valid PDF file.");
        fileInput.value = "";
        return;
    }

    if (file.size === 0) {
        showStatus("The selected file is empty.");
        fileInput.value = "";
        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        showStatus("Maximum file size is 20 MB.");
        fileInput.value = "";
        return;
    }

    selectedFile = file;

    fileName.textContent = file.name;

    fileSize.textContent =
        (file.size / (1024 * 1024)).toFixed(2) + " MB";

    fileCard.hidden = false;

    uploadBtn.disabled = false;

    showStatus("");
}

// Remove selected file
removeBtn.addEventListener("click", () => {

    selectedFile = null;

    fileInput.value = "";

    fileCard.hidden = true;

    uploadBtn.disabled = true;

    showStatus("");
});

// Drag over
dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("drag-over");
});

// Drag leave
dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
});

// Drop file
dropZone.addEventListener("drop", (event) => {

    event.preventDefault();

    dropZone.classList.remove("drag-over");

    const file = event.dataTransfer.files[0];

    handleFile(file);
});

// Upload button



// uploadBtn.addEventListener("click", () => {

//     if (!selectedFile) return;

//     showStatus(
//         "Frontend ready! Backend API integration is the next step."
//     );

//     console.log("Selected PDF:", selectedFile);
// });




const API_URL = "http://127.0.0.1:8000/api";

uploadBtn.addEventListener("click", async () => {

    if (!selectedFile) return;

    const formData = new FormData();

    formData.append("file", selectedFile);

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Processing Document...";

    showStatus("Uploading and processing your PDF...");

    try {

        const response = await fetch(`${API_URL}/upload`, {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Upload failed");
        }

        // Save session for subsequent chat requests
        sessionStorage.setItem("session_id", data.session_id);
        sessionStorage.setItem("document_id", data.document_id);

        showStatus(
            `Success! ${data.filename} indexed. ${data.chunks} chunks created.`
        );

        uploadBtn.textContent = "Document Ready ✓";

        console.log("Backend response:", data);

        // Chat page can now use this session
        // Uncomment after your chat page is ready:
        // window.location.href = "index.html";

    } catch (error) {

        console.error("Upload error:", error);

        showStatus(`Error: ${error.message}`);

        uploadBtn.disabled = false;
        uploadBtn.textContent = "Try Again →";
    }
});






// Status message
function showStatus(message) {
    statusMessage.textContent = message;
}
