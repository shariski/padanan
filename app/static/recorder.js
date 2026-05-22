// MediaRecorder flow for the recording screen (Phase 5). Vanilla JS — no
// framework, no build step (stack constraint). Records the answer, then POSTs the
// audio blob + prompt to /api/sessions.
(() => {
  const recorder = document.querySelector(".recorder");
  const recordBtn = document.getElementById("record-btn");
  const timerEl = document.getElementById("timer");
  const statusEl = document.getElementById("status");
  const processingEl = document.getElementById("processing");
  const processingText = document.getElementById("processing-text");
  let stageTimers = [];

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
    showProcessing();
  }

  // Staged progress for the single long /api/sessions request (upload → Whisper
  // transcription → LLM evaluation). The delays are approximate cues, not real
  // backend events — their job is to prove the page is alive and to name the
  // evaluation step, which is the slow part people were waiting on blindly.
  function showProcessing() {
    statusEl.textContent = "";
    processingText.textContent = "Uploading your recording…";
    processingEl.classList.remove("hidden");
    const stages = [
      [2500, "Transcribing your answer…"],
      [12000, "Evaluating your answer — this is the slow part. Keep this page open."],
    ];
    stageTimers = stages.map(([delay, msg]) =>
      setTimeout(() => { processingText.textContent = msg; }, delay)
    );
  }

  function hideProcessing() {
    stageTimers.forEach(clearTimeout);
    stageTimers = [];
    processingEl.classList.add("hidden");
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
      window.location = data.redirect; // -> /sessions/<id> (transcript view)
    } catch (err) {
      hideProcessing();
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
