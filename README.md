# RAG Assistant

Run these commands from the project folder. The frontend is plain HTML,
CSS, and JavaScript, so it does not need npm.

## Start the backend — terminal 1

```bash
cd "/Volumes/Sambu 1/Python project"
./venv/bin/python -m uvicorn Backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Wait for `Application startup complete.` Loading the embedding model can
take time, especially on the first run when its files must be downloaded.
Keep this terminal open.

Check the backend at <http://127.0.0.1:8000/> or open the API documentation
at <http://127.0.0.1:8000/docs>.

## Start the frontend — terminal 2

```bash
cd "/Volumes/Sambu 1/Python project"
./venv/bin/python -m http.server 5500 --bind 127.0.0.1 --directory Frontend
```

Open <http://127.0.0.1:5500/> and ask a question about your documents.
Serve the frontend through this address instead of opening `index.html`
directly. Port 5500 is allowed by the backend's CORS settings.

Press `Ctrl+C` in each terminal to stop its server.

## Configuration

The project-root `.env` file must contain your own Google API key:

```dotenv
GOOGLE_API_KEY=your_google_api_key
CHROMA_COLLECTION=rag_documents_v2
```

Keep the API key in `.env`, never in the frontend. The chatbot loads the
existing `db/chroma_local` database. Its collection must match the ingestion
pipeline (`rag_documents_v2`). `CHROMA_DIRECTORY`, if set, can be absolute
or relative to the project folder. `GEMINI_MODEL` can override the model in
`history_aware_generation.py`.

If you need to index new documents, put them in `docs/` and run from the
project folder:

```bash
./venv/bin/python ingestion_pipeline.py
```

## Troubleshooting

- **Failed to fetch:** confirm the backend reports startup complete and
  <http://127.0.0.1:8000/> opens. Use port 5500 for the frontend.
- **404 for `/session` or `/chat`:** the API base in `Frontend/app.js` must
  be `http://127.0.0.1:8000` without a trailing slash. Refresh the browser
  after changing JavaScript.
- **Invalid or expired session:** click **New Chat** after restarting the
  backend. Conversations are stored in memory.
- **Address already in use:** stop the previous server with `Ctrl+C` before
  starting another on the same port.
- **Google API errors:** check the key, model access, and quota for your
  Google project. The backend terminal shows the request error.
