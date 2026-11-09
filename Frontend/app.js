
const API = "http://127.0.0.1:8000";

const chatBox = document.getElementById("chat-box");
const chatForm = document.getElementById("chat-form");
const input = document.getElementById("question");
const sendButton = chatForm.querySelector("button");

let sessionId = null;
let busy = false;

function addMessage(text, role) {
    const element = document.createElement("div");
    element.className = `message ${role}`;
    element.textContent = text;

    chatBox.appendChild(element);
    chatBox.scrollTop = chatBox.scrollHeight;

    return element;
}

async function createSession() {
    const response = await fetch(`${API}/session`, {
        method: "POST"
    });

    if (!response.ok) {
        throw new Error("Could not create session");
    }

    const data = await response.json();
    sessionId = data.session_id;
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (busy) return;

    const question = input.value.trim();
    if (!question) return;

    busy = true;
    sendButton.disabled = true;
    input.value = "";

    addMessage(question, "user");
    const reply = addMessage("Thinking...", "ai");

    try {
        if (!sessionId) {
            await createSession();
        }

        const response = await fetch(`${API}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question,
                session_id: sessionId
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Request failed"
            );
        }

        reply.textContent = data.answer;

        if (data.sources?.length) {
            const sources = document.createElement("div");
            sources.className = "sources";

            // These are retrieved sources, not
            // necessarily all cited by the answer.
            sources.textContent = "Retrieved sources: " +
                data.sources.map(s => {
                    const location = s.slide
                        ? `Slide ${s.slide}`
                        : s.page
                        ? `Page ${s.page}`
                        : "";

                    return `${s.reference} ${s.file} ${location}`;
                }).join(", ");

            reply.appendChild(sources);
        }

    } catch (error) {
        reply.textContent = "Error: " + error.message;
    } finally {
        busy = false;
        sendButton.disabled = false;
    }
});

document.getElementById("new-chat")
    .addEventListener("click", async () => {
        if (busy) return;

        try {
            await createSession();
            chatBox.replaceChildren();
            addMessage("New conversation started.", "ai");
        } catch (error) {
            addMessage(error.message, "ai");
        }
    });
