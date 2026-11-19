/**
 * RAG AI - AI Chatbot Interface Controller
 * Powers the core conversational experience, markdown rendering,
 * source citations, copy actions, and prompt recommendations.
 */

document.addEventListener("DOMContentLoaded", () => {
    initChat();
});

let currentSessionId = null;
let isGenerating = false;

function initChat() {
    const chatInput = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");
    const chatForm = document.getElementById("chatForm");
    const viewport = document.getElementById("chatViewport");
    const renameBtn = document.getElementById("renameConvBtn");

    // 1. Load active conversation or start a fresh one
    bootstrapConversation();

    // 2. Multiline Auto-Resize Textarea
    if (chatInput) {
        chatInput.addEventListener("input", () => {
            chatInput.style.height = "auto";
            chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + "px";
            if (sendBtn) {
                sendBtn.disabled = !chatInput.value.trim() || isGenerating;
            }
        });

        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!isGenerating && chatInput.value.trim()) {
                    handleSendMessage();
                }
            }
        });
    }

    // 3. Form Submission
    if (chatForm) {
        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            if (!isGenerating && chatInput.value.trim()) {
                handleSendMessage();
            }
        });
    }

    // 4. Rename Active Conversation Header Button
    if (renameBtn) {
        renameBtn.addEventListener("click", () => {
            const activeConv = window.conversationHistory.getActiveConversation();
            if (activeConv) {
                const newTitle = window.prompt("Rename this conversation:", activeConv.title);
                if (newTitle && newTitle.trim()) {
                    window.conversationHistory.renameConversation(activeConv.id, newTitle.trim());
                    updateConversationTitleDisplay(newTitle.trim());
                    window.renderSidebarHistory();
                }
            }
        });
    }

    // Bind global helpers
    window.loadConversation = loadConversation;
    window.startNewConversation = startNewConversation;
    window.onActiveConversationDeleted = () => {
        bootstrapConversation();
    };
    window.updateConversationTitleDisplay = updateConversationTitleDisplay;
}

/**
 * Bootstrap or recover conversation state.
 */
async function bootstrapConversation() {
    let activeConv = window.conversationHistory.getActiveConversation();

    if (!activeConv) {
        await startNewConversation();
    } else {
        currentSessionId = activeConv.id;
        updateConversationTitleDisplay(activeConv.title);
        renderMessages(activeConv.messages);
    }
}

/**
 * Start a brand-new conversation session.
 */
async function startNewConversation() {
    const sendBtn = document.getElementById("sendBtn");
    if (sendBtn) sendBtn.disabled = true;

    try {
        const session = await window.ragApi.createSession();
        currentSessionId = session.session_id;

        const newConv = window.conversationHistory.createConversation(
            currentSessionId,
            "New Conversation"
        );

        updateConversationTitleDisplay(newConv.title);
        renderMessages([]);
        window.renderSidebarHistory();
    } catch (err) {
        console.error("Error creating session:", err);
        // Fallback local session ID if backend is starting up
        currentSessionId = "local_" + Date.now();
        window.conversationHistory.createConversation(currentSessionId, "New Conversation");
        renderMessages([]);
        window.renderSidebarHistory();
    } finally {
        if (sendBtn) sendBtn.disabled = false;
    }
}

/**
 * Switch and load an existing conversation.
 */
function loadConversation(convId) {
    const conv = window.conversationHistory.loadAll().find(c => c.id === convId);
    if (!conv) return;

    currentSessionId = conv.id;
    updateConversationTitleDisplay(conv.title);
    renderMessages(conv.messages);
}

/**
 * Update the title shown in the chat header.
 */
function updateConversationTitleDisplay(title) {
    const titleEl = document.getElementById("convTitleDisplay");
    if (titleEl) {
        titleEl.textContent = title || "New Conversation";
        titleEl.title = title || "New Conversation";
    }
}

/**
 * Render message list or show welcome screen if empty.
 */
function renderMessages(messages) {
    const container = document.getElementById("chatContentWrap");
    if (!container) return;

    container.innerHTML = "";

    if (!messages || messages.length === 0) {
        renderWelcomeScreen(container);
        return;
    }

    messages.forEach((msg) => {
        if (msg.role === "user") {
            appendUserMessage(msg.text, false);
        } else {
            appendAiMessage(msg.text, msg.sources, false);
        }
    });

    scrollToBottom();
}

/**
 * Render the Welcome Hero Screen with suggested questions.
 */
function renderWelcomeScreen(container) {
    const welcome = document.createElement("div");
    welcome.className = "welcome-screen";
    welcome.id = "welcomeScreen";

    welcome.innerHTML = `
        <div class="welcome-badge-icon">✦</div>
        <h1 class="welcome-title">Welcome to RAG AI</h1>
        <p class="welcome-desc">
            Your personal AI document assistant. Upload your PDFs and ask questions to explore their contents.
        </p>
        <div class="suggested-prompts-grid">
            <div class="prompt-card" data-prompt="Summarise my uploaded documents.">
                <span class="prompt-card-icon">⚡</span>
                <span class="prompt-card-text">Summarise my uploaded documents.</span>
                <span class="prompt-card-sub">Get an executive overview</span>
            </div>
            <div class="prompt-card" data-prompt="What are the main topics?">
                <span class="prompt-card-icon">📌</span>
                <span class="prompt-card-text">What are the main topics?</span>
                <span class="prompt-card-sub">Extract key subjects covered</span>
            </div>
            <div class="prompt-card" data-prompt="Explain the important concepts.">
                <span class="prompt-card-icon">💡</span>
                <span class="prompt-card-text">Explain the important concepts.</span>
                <span class="prompt-card-sub">Deep dive into critical details</span>
            </div>
            <div class="prompt-card" data-prompt="Find specific information in my PDFs.">
                <span class="prompt-card-icon">🔍</span>
                <span class="prompt-card-text">Find specific information in my PDFs.</span>
                <span class="prompt-card-sub">Query facts, numbers and figures</span>
            </div>
        </div>
    `;

    // Click suggested questions
    welcome.querySelectorAll(".prompt-card").forEach((card) => {
        card.addEventListener("click", () => {
            const promptText = card.dataset.prompt;
            const chatInput = document.getElementById("chatInput");
            if (chatInput) {
                chatInput.value = promptText;
                handleSendMessage();
            }
        });
    });

    container.appendChild(welcome);
}

/**
 * Handle sending a question to the backend.
 */
async function handleSendMessage() {
    const chatInput = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");
    const question = chatInput.value.trim();
    if (!question || isGenerating) return;

    // Clear welcome screen if visible
    const welcome = document.getElementById("welcomeScreen");
    if (welcome) welcome.remove();

    // 1. Render User Message
    appendUserMessage(question, true);
    chatInput.value = "";
    chatInput.style.height = "auto";

    // 2. Record in Local History
    window.conversationHistory.addMessage(currentSessionId, "user", question);
    const activeConv = window.conversationHistory.getActiveConversation();
    if (activeConv) updateConversationTitleDisplay(activeConv.title);
    window.renderSidebarHistory();

    // 3. Set loading state
    isGenerating = true;
    if (sendBtn) sendBtn.disabled = true;
    const thinkingRow = showThinkingIndicator();
    scrollToBottom();

    try {
        // 4. Send request to FastAPI backend with auto-recovery for restarted sessions
        let result;
        try {
            result = await window.ragApi.sendMessage(question, currentSessionId);
        } catch (apiErr) {
            if (apiErr.message && apiErr.message.toLowerCase().includes("session")) {
                console.warn("Session expired or missing on backend. Auto-refreshing session and retrying...");
                const newSession = await window.ragApi.createSession();
                currentSessionId = newSession.session_id;

                const activeConv = window.conversationHistory.getActiveConversation();
                if (activeConv) {
                    activeConv.id = currentSessionId;
                    window.conversationHistory.setActiveId(currentSessionId);
                    window.conversationHistory.saveAll();
                }
                result = await window.ragApi.sendMessage(question, currentSessionId);
            } else {
                throw apiErr;
            }
        }

        // Remove thinking indicator
        thinkingRow.remove();

        // 5. Append AI Message
        appendAiMessage(result.answer, result.sources, true);

        // 6. Record in Local History
        window.conversationHistory.addMessage(
            currentSessionId,
            "ai",
            result.answer,
            result.sources
        );
        window.renderSidebarHistory();

    } catch (err) {
        console.error("Chat error:", err);
        thinkingRow.remove();

        // Error message bubble
        appendAiMessage(
            `**Error:** ${err.message}\n\n*Tip: Check that your FastAPI backend is running on \`http://127.0.0.1:8000\` and contains indexed documents.*`,
            [],
            true
        );
    } finally {
        isGenerating = false;
        if (sendBtn) sendBtn.disabled = !chatInput.value.trim();
        scrollToBottom();
    }
}

/**
 * Append a user message row to the chat viewport.
 */
function appendUserMessage(text, animate = true) {
    const container = document.getElementById("chatContentWrap");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "message-row user";
    if (!animate) row.style.animation = "none";

    row.innerHTML = `
        <div class="message-bubble user">${escapeHtml(text)}</div>
    `;

    container.appendChild(row);
    if (animate) scrollToBottom();
}

/**
 * Append an AI message row with Markdown, citations, and actions.
 */
function appendAiMessage(rawText, sources = [], animate = true) {
    const container = document.getElementById("chatContentWrap");
    if (!container) return;

    const row = document.createElement("div");
    row.className = "message-row ai";
    if (!animate) row.style.animation = "none";

    // Parse Markdown safely
    const formattedHtml = parseMarkdown(rawText);

    // Citations HTML
    let citationsHtml = "";
    if (Array.isArray(sources) && sources.length > 0) {
        const chipsHtml = sources.map((s) => {
            const loc = s.location || (s.page ? `Page ${s.page}` : (s.slide ? `Slide ${s.slide}` : ""));
            const ref = s.reference || "[*]";
            const file = s.file || "Document";
            return `
                <div class="citation-chip" title="${escapeHtml(file)} (${escapeHtml(loc)})">
                    <span class="citation-ref">${escapeHtml(ref)}</span>
                    <span class="citation-file">${escapeHtml(file)}</span>
                    ${loc ? `<span class="citation-loc">${escapeHtml(loc)}</span>` : ""}
                </div>
            `;
        }).join("");

        citationsHtml = `
            <div class="citations-wrap">
                <div class="citations-header">
                    <span>📚</span> Retrieved Sources (${sources.length})
                </div>
                <div class="citations-grid">
                    ${chipsHtml}
                </div>
            </div>
        `;
    }

    row.innerHTML = `
        <div class="ai-avatar">✦</div>
        <div class="message-bubble ai">
            <div class="ai-text">${formattedHtml}</div>
            ${citationsHtml}
            <div class="message-actions">
                <button class="action-pill-btn copy-btn" title="Copy answer to clipboard">
                    <span>📋</span> Copy
                </button>
                <button class="action-pill-btn feedback-btn" data-type="up" title="Helpful answer">
                    <span>👍</span>
                </button>
                <button class="action-pill-btn feedback-btn" data-type="down" title="Not helpful">
                    <span>👎</span>
                </button>
            </div>
        </div>
    `;

    // Copy Button Handler
    const copyBtn = row.querySelector(".copy-btn");
    copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(rawText).then(() => {
            copyBtn.innerHTML = `<span>✓</span> Copied!`;
            setTimeout(() => {
                copyBtn.innerHTML = `<span>📋</span> Copy`;
            }, 2000);
        });
    });

    // Feedback Buttons Handler
    const feedbackBtns = row.querySelectorAll(".feedback-btn");
    feedbackBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            feedbackBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });

    container.appendChild(row);
    if (animate) scrollToBottom();
}

/**
 * Show a sleek thinking animation row.
 */
function showThinkingIndicator() {
    const container = document.getElementById("chatContentWrap");
    const row = document.createElement("div");
    row.className = "message-row ai thinking-row";

    row.innerHTML = `
        <div class="ai-avatar">✦</div>
        <div class="thinking-dots">
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
        </div>
    `;

    container.appendChild(row);
    return row;
}

/**
 * Scroll chat viewport to the latest message.
 */
function scrollToBottom() {
    const viewport = document.getElementById("chatViewport");
    if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
    }
}

/**
 * Parse Markdown to HTML. Uses marked.js if loaded, or a built-in safe parser.
 */
function parseMarkdown(text) {
    if (!text) return "";

    let html = "";
    if (window.marked && typeof window.marked.parse === "function") {
        try {
            html = window.marked.parse(text);
        } catch (e) {
            console.warn("marked.js parse failed, falling back to built-in parser:", e);
            html = fallbackParseMarkdown(text);
        }
    } else {
        html = fallbackParseMarkdown(text);
    }

    // Wrap tables in responsive container if not already wrapped
    html = html.replace(/(<table[\s\S]*?<\/table>)/gi, (match) => {
        return `<div class="table-wrap">${match}</div>`;
    });

    // Style inline citations like [1] or 【1】
    html = html.replace(/(?:\[(\d+)\]|【(\d+)】)/g, (match, p1, p2) => {
        const num = p1 || p2;
        return `<span class="inline-cite">[${num}]</span>`;
    });

    return html;
}

/**
 * Built-in safe Markdown fallback parser (runs offline or without marked.js).
 */
function fallbackParseMarkdown(text) {
    let escaped = escapeHtml(text);

    // Code blocks ```code```
    escaped = escaped.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
    });

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Horizontal rules
    escaped = escaped.replace(/^---$/gim, "<hr>");

    // Headers
    escaped = escaped.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    escaped = escaped.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    escaped = escaped.replace(/^# (.*$)/gim, "<h1>$1</h1>");

    // Bold & Italics
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Blockquotes
    escaped = escaped.replace(/^> (.*$)/gim, "<blockquote>$1</blockquote>");

    // Tables
    escaped = escaped.replace(/(?:(?:^|\n)\|[^\n]+\|\r?\n\|[-: |]+\|\r?\n(?:\|[^\n]+\|\r?\n?)+)/g, (tableText) => {
        const rows = tableText.trim().split(/\r?\n/).filter(r => r.trim().startsWith("|"));
        if (rows.length < 2) return tableText;
        const parseRow = (r) => r.split("|").slice(1, -1).map(c => c.trim());
        const headers = parseRow(rows[0]);
        const bodyRows = rows.slice(2).map(parseRow);
        return `<table><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${bodyRows.map(row => `<tr>${row.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    });

    // Unordered lists
    escaped = escaped.replace(/^\* (.*$)/gim, "<ul><li>$1</li></ul>");
    escaped = escaped.replace(/^- (.*$)/gim, "<ul><li>$1</li></ul>");
    escaped = escaped.replace(/<\/ul>\s*<ul>/g, "");

    // Ordered lists
    escaped = escaped.replace(/^\d+\. (.*$)/gim, "<ol><li>$1</li></ol>");
    escaped = escaped.replace(/<\/ol>\s*<ol>/g, "");

    // Line breaks to paragraphs
    const paragraphs = escaped.split(/\n{2,}/).map(p => {
        p = p.trim();
        if (p.startsWith("<h") || p.startsWith("<pre") || p.startsWith("<ul") || p.startsWith("<ol") || p.startsWith("<block") || p.startsWith("<table") || p.startsWith("<hr")) {
            return p;
        }
        return `<p>${p.replace(/\n/g, "<br>")}</p>`;
    });

    return paragraphs.join("");
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
