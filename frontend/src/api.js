export async function askHelp({ text, audioBlob, files, language = "en" }) {
  const form = new FormData();
  form.append("language", language);
  if (text && text.trim()) {
    form.append("text", text.trim());
  }
  if (audioBlob) {
    const extension = audioBlob.type.includes("mp4") ? "m4a" : "webm";
    form.append("audio", audioBlob, `voice.${extension}`);
  }
  for (const file of files || []) {
    form.append("files", file);
  }
  const response = await fetch("/api/ask", {
    method: "POST",
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = language === "en"
      ? "The server could not respond. Check that the backend is running."
      : "सर्वर से जवाब नहीं मिला। जाँचें कि backend चालू है।";
    throw new Error(data.detail || fallback);
  }
  return data;
}

export async function transcribeAudio(audioBlob, language = "en") {
  const form = new FormData();
  const extension = audioBlob.type.includes("mp4") ? "m4a" : "webm";
  form.append("audio", audioBlob, `voice.${extension}`);
  const response = await fetch(`/api/transcribe?language=${encodeURIComponent(language)}`, {
    method: "POST",
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = language === "en"
      ? "Speech recognition failed. Try again or type your message."
      : "आवाज़ लिखी नहीं जा सकी। फिर कोशिश करें या संदेश लिखें।";
    throw new Error(data.detail || fallback);
  }
  return (data.transcript || "").trim();
}

export async function health() {
  const response = await fetch("/api/health");
  return response.json();
}

export async function listCases(language = "en") {
  const response = await fetch("/api/cases");
  if (!response.ok) {
    throw new Error(language === "en" ? "Previous cases could not be loaded." : "पुराने केस नहीं खुल सके।");
  }
  return (await response.json()).cases || [];
}

export async function getCase(id, language = "en") {
  const response = await fetch(`/api/cases/${id}?language=${language}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = language === "en" ? "This case could not be opened." : "यह केस नहीं खुल सका।";
    throw new Error(data.detail || fallback);
  }
  return data;
}
