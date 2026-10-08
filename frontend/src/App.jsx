import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { askHelp, getCase, listCases, transcribeAudio } from "./api.js";

const COPY = {
  hi: {
    title: "श्रम सहायक",
    description: "बोलकर या कागज़ भेजकर श्रम सहायता लें।",
    subtitle: "बोलकर या कागज़ भेजकर मदद लें",
    language: "भाषा चुनें",
    microphone: "माइक्रोफोन",
    startRecording: "बोलने के लिए दबाएँ",
    recording: "बोल रहे हैं… रोकने के लिए फिर दबाएँ",
    transcribing: "आवाज़ लिखी जा रही है…",
    recorded: "आवाज़ रिकॉर्ड हो गई",
    transcribed: "आवाज़ का पाठ नीचे जोड़ दिया है",
    recordingError: "रिकॉर्डिंग नहीं हुई। फिर कोशिश करें या नीचे लिखें।",
    microphoneError: "माइक चालू नहीं हुआ। अनुमति दें या नीचे लिखें।",
    removeRecording: "रिकॉर्डिंग हटाएँ",
    textLabel: "या यहाँ लिखें",
    textPlaceholder: "जैसे: तीन महीने से सैलरी नहीं मिली",
    documents: "फोटो या PDF जोड़ें",
    removeFiles: "कागज़ हटाएँ",
    fileTooLarge: "हर फ़ाइल 20 MB से छोटी होनी चाहिए।",
    submit: "मदद लें",
    loading: "जवाब तैयार हो रहा है…",
    empty: "पहले बोलें या लिखें।",
    genericError: "कुछ गड़बड़ हो गई। फिर कोशिश करें।",
    unknown: "पक्की जानकारी नहीं मिली। e-Shram हेल्पलाइन 14434 पर कॉल करें।",
    documentChecks: "दस्तावेज़ में ध्यान दें",
    heard: "सुना गया",
    source: "आधिकारिक स्रोत",
    history: "पहले के केस",
    historyError: "पुराने केस अभी नहीं दिख रहे।",
    historyEmpty: "अभी कोई केस नहीं है।",
    crisis: {
      unpaid_wages: "वेतन नहीं मिला",
      illegal_termination: "नौकरी से निकाला",
      workplace_injury: "काम पर चोट",
      harassment: "परेशानी / उत्पीड़न",
      documents_missing: "कागज़ नहीं हैं",
      other: "अन्य समस्या",
    },
    urgency: { low: "कम", medium: "सामान्य", high: "जल्दी", critical: "तुरंत" },
  },
  en: {
    title: "Shram Sahayak",
    description: "Get worker support by speaking or sharing a document.",
    subtitle: "Get help by speaking or sharing a document",
    language: "Choose language",
    microphone: "Microphone",
    startRecording: "Tap to speak",
    recording: "Listening… tap again to stop",
    transcribing: "Transcribing your recording…",
    recorded: "Recording ready",
    transcribed: "Transcript added to the text box",
    recordingError: "Recording failed. Try again or type below.",
    microphoneError: "Microphone unavailable. Allow access or type below.",
    removeRecording: "Remove recording",
    textLabel: "Or type here",
    textPlaceholder: "For example: I have not been paid for three months",
    documents: "Add a photo or PDF",
    removeFiles: "Remove files",
    fileTooLarge: "Each file must be smaller than 20 MB.",
    submit: "Get help",
    loading: "Preparing your answer…",
    empty: "Speak or type a message first.",
    genericError: "Something went wrong. Please try again.",
    unknown: "We could not find confirmed information. Call the e-Shram helpline at 14434.",
    documentChecks: "Document checks",
    heard: "Transcript",
    source: "Official source",
    history: "Previous cases",
    historyError: "Previous cases are not available right now.",
    historyEmpty: "No cases yet.",
    crisis: {
      unpaid_wages: "Unpaid wages",
      illegal_termination: "Job termination",
      workplace_injury: "Workplace injury",
      harassment: "Harassment",
      documents_missing: "Missing documents",
      other: "Other issue",
    },
    urgency: { low: "Low", medium: "Moderate", high: "High", critical: "Immediate" },
  },
};

export default function App() {
  const [language, setLanguage] = useState("en");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [transcriptReady, setTranscriptReady] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [cases, setCases] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const ui = COPY[language];
  const resultUi = COPY[result?.language || language];

  useEffect(() => {
    listCases().then(setCases).catch(() => setHistoryError(true));
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = ui.title;
    document.querySelector('meta[name="description"]')?.setAttribute("content", ui.description);
  }, [language, ui.title]);

  async function toggleMic() {
    setError("");
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("unsupported");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        stream.getTracks().forEach((t) => t.stop());
        setTranscribing(true);
        setError("");
        try {
          const transcript = await transcribeAudio(blob, language);
          if (!transcript) throw new Error(ui.genericError);
          setText((current) => current.trim() ? `${current.trim()}\n${transcript}` : transcript);
          setTranscriptReady(true);
          setAudioBlob(null);
        } catch (transcriptionError) {
          setAudioBlob(blob);
          setError(transcriptionError.message || ui.genericError);
        } finally {
          setTranscribing(false);
        }
      };
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        setError(ui.recordingError);
      };
      recorderRef.current = recorder;
      recorder.start();
      setTranscriptReady(false);
      setRecording(true);
    } catch {
      setError(ui.microphoneError);
    }
  }

  function updateFiles(fileList) {
    const selected = Array.from(fileList || []);
    if (selected.some((file) => file.size > 20 * 1024 * 1024)) {
      setError(ui.fileTooLarge);
      return;
    }
    setError("");
    setFiles(selected);
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (transcribing) return;
    setError("");
    setResult(null);
    if (!audioBlob && !text.trim() && files.length === 0) {
      setError(ui.empty);
      return;
    }
    setLoading(true);
    try {
      const data = await askHelp({ text, audioBlob, files, language });
      setResult({ ...data, language: data.language || language });
      const latestCases = await listCases();
      setCases(latestCases);
      setHistoryError("");
    } catch (err) {
      setError(err.message || ui.genericError);
    } finally {
      setLoading(false);
    }
  }

  async function openCase(id) {
    setError("");
    try {
      const data = await getCase(id, language);
      setResult({ ...data, language: data.language || language });
    } catch (err) {
      setError(err.message || ui.genericError);
    }
  }

  return (
    <main className={`page ${language === "en" ? "english" : "hindi"}`}>
      <header className="page-header">
        <div className="brand">
          <h1>{ui.title}</h1>
          <p className="sub">{ui.subtitle}</p>
        </div>
        <div className="language-switch" role="group" aria-label={ui.language}>
          <button
            type="button"
            className={language === "hi" ? "selected" : ""}
            aria-pressed={language === "hi"}
            onClick={() => {
              setLanguage("hi");
              setError("");
            }}
          >
            हिन्दी
          </button>
          <button
            type="button"
            className={language === "en" ? "selected" : ""}
            aria-pressed={language === "en"}
            onClick={() => {
              setLanguage("en");
              setError("");
            }}
          >
            English
          </button>
        </div>
      </header>

      <form onSubmit={onSubmit}>
        <button
          type="button"
          className={`mic ${recording ? "live" : ""} ${audioBlob && !recording ? "ready" : ""}`}
          onClick={toggleMic}
          aria-label={recording ? ui.recording : ui.microphone}
          title={recording ? ui.recording : ui.microphone}
          disabled={loading || transcribing}
        >
          {recording ? <Square size={25} strokeWidth={2.5} /> : <Mic size={38} strokeWidth={2} />}
        </button>
        <p className="hint" aria-live="polite">
          {transcribing
            ? ui.transcribing
            : recording
            ? ui.recording
            : transcriptReady
              ? ui.transcribed
              : audioBlob
              ? ui.recorded
              : ui.startRecording}
        </p>
        {audioBlob && !recording && (
          <button className="text-button" type="button" onClick={() => setAudioBlob(null)}>
            {ui.removeRecording}
          </button>
        )}

        <label className="label" htmlFor="text">
          {ui.textLabel}
        </label>
        <textarea
          id="text"
          rows={4}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setTranscriptReady(false);
          }}
          placeholder={ui.textPlaceholder}
        />

        <label className="file" htmlFor="documents">
          <span>{ui.documents}</span>
          <input
            id="documents"
            type="file"
            aria-label={ui.documents}
            accept="image/jpeg,image/png,application/pdf,.jpg,.jpeg,.png,.pdf"
            multiple
            onChange={(e) => updateFiles(e.target.files)}
          />
        </label>
        {files.length > 0 && (
          <div className="file-list">
            <ul className="files">
              {files.map((f) => (
                <li key={`${f.name}-${f.lastModified}`}>{f.name}</li>
              ))}
            </ul>
            <button className="text-button" type="button" onClick={() => setFiles([])}>
              {ui.removeFiles}
            </button>
          </div>
        )}

        <button className="primary" type="submit" disabled={loading || transcribing}>
          {transcribing ? ui.transcribing : loading ? ui.loading : ui.submit}
        </button>
      </form>

      {error && <div className="error" role="alert">{error}</div>}

      {result && (
        <section className="result">
          {result.unknown && (
            <div className="warn">
              {resultUi.unknown}
            </div>
          )}
          <p className="crisis">
            {resultUi.crisis[result.crisis_type] || result.crisis_type}
            <span className={`badge ${result.urgency}`}>
              {resultUi.urgency[result.urgency] || result.urgency}
            </span>
          </p>
          <p className="summary">{result.summary_hi}</p>
          {result.document_issues?.length > 0 && (
            <section className="document-findings" aria-labelledby="document-findings-title">
              <h2 id="document-findings-title">{resultUi.documentChecks}</h2>
              <ul>
                {result.document_issues.map((finding, index) => (
                  <li key={`${finding.issue}-${index}`}>
                    <strong>{finding.issue}</strong>
                    <span>{finding.action}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <ol>
            {(result.steps_hi || []).map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
          <div className="links">
            {(result.sources || []).map((s) => (
              <a key={`${s.url}-${s.name}`} href={s.url} target="_blank" rel="noreferrer">
                {s.name || resultUi.source}
              </a>
            ))}
          </div>
          {result.transcript && (
            <p className="heard">{resultUi.heard}: {result.transcript}</p>
          )}
        </section>
      )}

      <section className="history" aria-labelledby="history-title">
        <h2 id="history-title">{ui.history}</h2>
        {historyError && <p className="history-error">{ui.historyError}</p>}
        {cases.length === 0 && !historyError && <p className="history-empty">{ui.historyEmpty}</p>}
        {cases.length > 0 && (
          <ul>
            {cases.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => openCase(item.id)}>
                  <span>{ui.crisis[item.crisis_type] || item.crisis_type}</span>
                  <small>{item.summary_hi}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
