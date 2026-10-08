# Shram Sahayak (श्रम सहायक)

Phase 1 worker-crisis helper: **Hindi/English voice or text + document → one Gemini answer** grounded in a local knowledge base. The interface and generated guidance follow the Hindi/English switch. No agent loops. No text-to-speech.

This is **not legal advice**. Official steps always go through government portals.

## Free API keys

1. Groq (speech-to-text): [https://console.groq.com/](https://console.groq.com/)
2. Gemini (guidance): [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

From the project root, copy `.env.example` to `.env` and paste the keys:

```powershell
Copy-Item .env.example .env
```

Then set the values in `.env`:

```dotenv
GROQ_API_KEY=...
GEMINI_API_KEY=...
```

## Windows PowerShell — run

Open **two** terminals.

### 1. Backend

```powershell
cd .\backend
py -3.11 -m venv .venv-py311
.\.venv-py311\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.ingest
uvicorn app.main:app --reload --port 8000
```

First ingest downloads the MiniLM embedding model (one-time). Wait until it prints how many chunks were stored.

On Windows, Python 3.11 is recommended because Chroma's `chroma-hnswlib` dependency has a prebuilt CPython 3.11 wheel. If you prefer Python 3.13, install the **Desktop development with C++** workload from Microsoft C++ Build Tools before installing requirements; otherwise pip tries to compile `hnswlib` and fails when MSVC is unavailable.

### 2. Frontend

```powershell
cd .\frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

If `Activate.ps1` is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Backend tests

Run these from `backend` after installing `requirements.txt`:

```powershell
python -m unittest discover -s tests -v
```

The tests mock Gemini, Groq, and Chroma, so they do not need API keys, model downloads, or paid services. They cover output/source validation, document findings, the JSON retry, text-only and audio requests, PDF and image handling, invalid input, missing Groq keys, and SQLite case history.

## Demo and live API checks

Start both servers using the commands above, then open `http://localhost:5173`. Try these flows:

1. Type `तीन महीने से वेतन नहीं मिला` and press **मदद लें**. Confirm Hindi steps, a SAMADHAN source button, and a new entry under **पहले के केस**.
2. Switch to **English**, type `I have not been paid for three months`, and submit. Confirm the answer and urgency label appear in English.
3. Click the microphone, allow browser access, speak Hindi or English, and stop. Groq transcribes the recording into the editable text box; review or correct it, then press **मदद लें / Get help**. Microphone access requires localhost or HTTPS.
4. Attach a payslip, notice, or work document with no typed question and submit. Review any **Document checks** / **दस्तावेज़ में ध्यान दें** findings. They describe visible omissions or inconsistencies and are not legal verification.
5. Type a question and attach a JPG or PNG to check same-call image review. Attach a text-based PDF to check PDF extraction.
6. Submit an empty form and an unsupported file type. Confirm the app shows a clear error in the selected language and does not save a case.
7. Open a prior case from **पहले के केस / Previous cases** and confirm saved answer language, document findings, steps, and source links return.

Check service health and saved cases from another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/cases
```

Call the text endpoint directly with the Windows `curl.exe` executable:

```powershell
curl.exe -sS -F "text=तीन महीने से वेतन नहीं मिला" http://127.0.0.1:8000/api/ask
```

For speech, replace the path with a local audio recording:

```powershell
curl.exe -sS -F "audio=@C:\path\to\voice.webm;type=audio/webm" http://127.0.0.1:8000/api/transcribe
```

To check missing-key messages, temporarily leave the corresponding `.env` value blank and restart the backend. `/api/transcribe` reports the missing Groq key; `/api/ask` reports the missing Gemini key. Restore the value and restart before the live demo.

## How it works

1. Browser records audio (or you type).
2. Groq Whisper turns speech into Hindi/English text.
3. PDF text is extracted; photos and document checks go to Gemini in the **same** generate call.
4. Chroma finds up to 5 related chunks from `backend/knowledge/`.
5. Gemini returns locale-matched steps, observed document issues, and verified source URLs.
6. URLs not in the knowledge base or allowlist are dropped.
7. Case is saved in SQLite (`backend/data/app.db`).

## Routes

| Method | Path | Use |
|--------|------|-----|
| GET | `/api/health` | Alive check |
| POST | `/api/transcribe` | Audio only |
| POST | `/api/ask` | Full pipeline |
| GET | `/api/cases` | Last 20 cases |
| GET | `/api/cases/{id}` | One case |

## Out of scope (Phase 1)

Read-aloud TTS, login, WhatsApp, Docker, dual-LLM verification, agent frameworks.
