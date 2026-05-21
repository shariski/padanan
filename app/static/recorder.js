// MediaRecorder flow for the recording screen (Phase 5). Vanilla JS — no
// framework, no build step (stack constraint). Records the answer, then POSTs the
// audio blob + prompt to /api/sessions.
(() => {
  const recorder = document.querySelector(".recorder");
  const recordBtn = document.getElementById("record-btn");
  const timerEl = document.getElementById("timer");
  const statusEl = document.getElementById("status");

  const promptText = recorder.dataset.promptText;
  const promptSource = recorder.dataset.promptSource;

  let mediaRecorder = null;
  let chunks = [];
  let timerId = null;
  let seconds = 0;

  // getUserMedia only exists in a secure context (localhost is OK; over Tailscale
  // it needs HTTPS). Flag it loudly rather than failing silently — see
  // docs/audio-pipeline.md.
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    recordBtn.disabled = true;
    statusEl.textContent =
      "Microphone unavailable — this page needs a secure context (localhost or " +
      "HTTPS). Over Tailscale, enable HTTPS via MagicDNS.";
    return;
  }

  function fmt(total) {
    const m = String(Math.floor(total / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function tick() {
    seconds += 1;
    timerEl.textContent = fmt(seconds);
    // Soft cap cues (product-spec §3.2): black <90s, amber 90–120s, red >120s.
    timerEl.classList.toggle("amber", seconds >= 90 && seconds < 120);
    timerEl.classList.toggle("red", seconds >= 120);
  }

  async function start() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      statusEl.textContent = `Microphone permission denied or unavailable (${err.name}).`;
      return;
    }
    chunks = [];
    seconds = 0;
    timerEl.textContent = "00:00";
    timerEl.className = "timer";
    statusEl.textContent = "";

    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      upload();
    };
    mediaRecorder.start();
    timerId = setInterval(tick, 1000);
    recordBtn.textContent = "■ Stop";
    recordBtn.classList.add("recording");
  }

  function stop() {
    clearInterval(timerId);
    mediaRecorder.stop();
    recordBtn.disabled = true;
    recordBtn.textContent = "● Record";
    recordBtn.classList.remove("recording");
    statusEl.textContent = "Uploading…";
  }

  async function upload() {
    const blob = new Blob(chunks, { type: mediaRecorder.mimeType });
    const form = new FormData();
    form.append("audio", blob, "recording");
    form.append("prompt_text", promptText);
    form.append("prompt_source", promptSource);
    try {
      const res = await fetch("/api/sessions", { method: "POST", body: form });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // Phase 6 will redirect to the analyzing screen here.
      statusEl.textContent =
        `Uploaded as session #${data.session_id} ` +
        `(${data.duration_seconds.toFixed(1)}s). Transcription + analysis wire in next.`;
    } catch (err) {
      statusEl.textContent = `Upload failed: ${err.message}`;
      recordBtn.disabled = false;
    }
  }

  recordBtn.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      stop();
    } else {
      start();
    }
  });
})();
