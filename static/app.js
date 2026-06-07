const state = {
  sessionId: null,
  userId: localStorage.getItem("speakingCoachUserId") || crypto.randomUUID(),
  recognition: null,
  listening: false,
  startedAt: 0,
  latestConfidence: null,
  finalTranscript: "",
  lastUserText: "",
  ttsMs: 0,
};

localStorage.setItem("speakingCoachUserId", state.userId);

const els = {
  scenario: document.querySelector("#scenario"),
  level: document.querySelector("#level"),
  autoListen: document.querySelector("#autoListen"),
  startBtn: document.querySelector("#startBtn"),
  micBtn: document.querySelector("#micBtn"),
  manualText: document.querySelector("#manualText"),
  sendTextBtn: document.querySelector("#sendTextBtn"),
  reviseBtn: document.querySelector("#reviseBtn"),
  messages: document.querySelector("#messages"),
  liveLine: document.querySelector("#liveLine"),
  scenarioTitle: document.querySelector("#scenarioTitle"),
  scenarioGoal: document.querySelector("#scenarioGoal"),
  slotProgress: document.querySelector("#slotProgress"),
  phonemes: document.querySelector("#phonemes"),
  corrections: document.querySelector("#corrections"),
  tips: document.querySelector("#tips"),
  pipeline: document.querySelector("#pipeline"),
  summaryBtn: document.querySelector("#summaryBtn"),
  deleteDataBtn: document.querySelector("#deleteDataBtn"),
  summary: document.querySelector("#summary"),
  overallScore: document.querySelector("#overallScore"),
  pronScore: document.querySelector("#pronScore"),
  fluencyScore: document.querySelector("#fluencyScore"),
  grammarScore: document.querySelector("#grammarScore"),
  pace: document.querySelector("#pace"),
  latency: document.querySelector("#latency"),
  intent: document.querySelector("#intent"),
  engineStatus: document.querySelector("#engineStatus"),
};

function speechRecognitionFactory() {
  return window.SpeechRecognition || window.webkitSpeechRecognition;
}

function supportsSpeech() {
  return Boolean(speechRecognitionFactory()) && "speechSynthesis" in window;
}

async function api(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "request_failed");
  }
  return data;
}

function addMessage(role, text, meta = "") {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  const who = role === "assistant" ? "AI Partner" : "You";
  node.innerHTML = `<small>${who}${meta ? ` · ${meta}` : ""}</small><span></span>`;
  node.querySelector("span").textContent = text;
  els.messages.appendChild(node);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function speak(text) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) {
      resolve(0);
      return;
    }
    const started = performance.now();
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(Math.round(performance.now() - started));
    };
    const timeoutMs = Math.min(5200, Math.max(1400, text.length * 45));
    window.setTimeout(finish, timeoutMs);
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.96;
    utterance.pitch = 1;
    utterance.onend = finish;
    utterance.onerror = finish;
    window.speechSynthesis.speak(utterance);
  });
}

function resetFeedback() {
  els.corrections.innerHTML = "";
  els.tips.innerHTML = "";
  els.phonemes.innerHTML = "";
  els.pipeline.innerHTML = "";
  els.intent.textContent = "-";
  ["overallScore", "pronScore", "fluencyScore", "grammarScore"].forEach((key) => {
    els[key].textContent = "0";
  });
  els.pace.textContent = "-";
  els.latency.textContent = "-";
  els.slotProgress.style.width = "0%";
}

function renderList(container, items, formatter) {
  container.innerHTML = "";
  items.filter(Boolean).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = formatter(item);
    container.appendChild(li);
  });
}

function renderPipeline(pipeline, ttsMs = state.ttsMs) {
  const rows = [
    ["ASR", pipeline.asrClientMs || 0],
    ["NLU", pipeline.nluMs || 0],
    ["Scoring", pipeline.scoringMs || 0],
    ["DM", pipeline.dmMs || 0],
    ["LLM", pipeline.llmMs || 0],
    ["TTS", ttsMs || 0],
  ];
  els.pipeline.innerHTML = "";
  rows.forEach(([label, ms]) => {
    const node = document.createElement("div");
    node.innerHTML = `<span>${label}</span><strong>${ms} ms</strong>`;
    els.pipeline.appendChild(node);
  });
}

function renderFeedback(data, clientRoundTripMs = 0) {
  els.overallScore.textContent = data.scores.overall;
  els.pronScore.textContent = data.scores.pronunciation;
  els.fluencyScore.textContent = data.scores.fluency;
  els.grammarScore.textContent = data.scores.grammar;
  els.intent.textContent = data.intent;
  els.pace.textContent = `${data.pronunciation.pace} · ${data.pronunciation.speechRateWpm} WPM`;
  els.latency.textContent = `${clientRoundTripMs || data.latencyMs} ms`;
  els.slotProgress.style.width = `${Math.round((data.slotCompletion || 0) * 100)}%`;

  renderList(els.phonemes, data.pronunciation.phonemeScores || [], (item) => `${item.unit}: ${item.gop} · ${item.tip}`);
  renderList(els.corrections, data.corrections || [], (item) => `${item.corrected} (${item.reason})`);
  renderList(els.tips, [...(data.expressionTips || []), data.pronunciation.feedback], (item) => item);
  renderPipeline(data.pipeline || {});
}

async function handleUserText(text, confidence = 0.8, durationSec = 3, asrClientMs = 0) {
  const cleanText = text.trim();
  if (!cleanText || !state.sessionId) {
    return;
  }
  state.lastUserText = cleanText;
  addMessage("user", cleanText);
  els.liveLine.textContent = "AI 正在组织回复...";
  els.micBtn.disabled = true;
  els.sendTextBtn.disabled = true;
  const roundTripStarted = performance.now();
  const data = await api("/api/respond", {
    sessionId: state.sessionId,
    text: cleanText,
    confidence,
    durationSec,
    asrClientMs,
  });
  const clientRoundTripMs = Math.round(performance.now() - roundTripStarted + asrClientMs);
  renderFeedback(data, clientRoundTripMs);
  addMessage("assistant", data.assistant, `${clientRoundTripMs} ms`);
  els.liveLine.textContent = "Ready";
  state.ttsMs = await speak(data.assistant);
  renderPipeline(data.pipeline || {}, state.ttsMs);
  els.micBtn.disabled = !supportsSpeech();
  els.sendTextBtn.disabled = false;
  els.reviseBtn.disabled = false;
  if (els.autoListen.checked && supportsSpeech()) {
    startListening();
  }
}

function configureRecognition() {
  if (!supportsSpeech()) {
    els.liveLine.textContent = "当前浏览器不支持语音 API，可使用文本输入继续练习。";
    els.micBtn.disabled = true;
    els.engineStatus.textContent = "文本模式";
    return;
  }

  const Recognition = speechRecognitionFactory();
  state.recognition = new Recognition();
  state.recognition.lang = "en-US";
  state.recognition.interimResults = true;
  state.recognition.continuous = false;
  state.recognition.maxAlternatives = 1;

  state.recognition.onstart = () => {
    state.listening = true;
    state.startedAt = performance.now();
    state.finalTranscript = "";
    state.latestConfidence = null;
    els.micBtn.classList.add("listening");
    els.micBtn.textContent = "正在聆听";
    els.liveLine.textContent = "Listening...";
  };

  state.recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const transcript = result[0].transcript.trim();
      if (result.isFinal) {
        state.finalTranscript += ` ${transcript}`;
        state.latestConfidence = result[0].confidence || state.latestConfidence;
      } else {
        interim += transcript;
      }
    }
    els.liveLine.textContent = interim || state.finalTranscript || "Listening...";
  };

  state.recognition.onend = () => {
    state.listening = false;
    els.micBtn.classList.remove("listening");
    els.micBtn.textContent = "点击说话";
    const text = state.finalTranscript.trim();
    if (!text) {
      els.liveLine.textContent = "未识别到语音，可以重说或手动输入。";
      els.micBtn.disabled = false;
      return;
    }
    const durationSec = (performance.now() - state.startedAt) / 1000;
    handleUserText(text, state.latestConfidence, durationSec, Math.round(durationSec * 1000)).catch((error) => {
      els.liveLine.textContent = error.message;
      els.micBtn.disabled = false;
      els.sendTextBtn.disabled = false;
    });
  };

  state.recognition.onerror = (event) => {
    state.listening = false;
    els.micBtn.classList.remove("listening");
    els.micBtn.textContent = "点击说话";
    els.liveLine.textContent = event.error || "speech_error";
  };
}

function startListening() {
  if (!state.recognition || state.listening || !state.sessionId) {
    return;
  }
  window.speechSynthesis.cancel();
  state.recognition.start();
}

function stopListening() {
  if (state.recognition && state.listening) {
    state.recognition.stop();
  }
}

async function startPractice() {
  stopListening();
  els.messages.innerHTML = "";
  els.summary.innerHTML = "";
  resetFeedback();
  const data = await api("/api/start", {
    scenario: els.scenario.value,
    level: els.level.value,
    userId: state.userId,
  });
  state.sessionId = data.sessionId;
  els.summaryBtn.disabled = false;
  els.sendTextBtn.disabled = false;
  els.micBtn.disabled = !supportsSpeech();
  els.scenarioTitle.textContent = `${data.scenario} · ${data.requiredSlots.length} 个任务点`;
  els.scenarioGoal.textContent = data.goal;
  els.engineStatus.textContent = data.engine.llm.includes("OpenAI") ? "AI 增强" : "本地对话管理";
  addMessage("assistant", data.opening, data.scenario);
  els.liveLine.textContent = data.goal;
  state.ttsMs = await speak(data.opening);
  if (els.autoListen.checked && supportsSpeech()) {
    startListening();
  }
}

async function sendManualText() {
  const text = els.manualText.value.trim();
  if (!text) {
    return;
  }
  els.manualText.value = "";
  const approxDuration = Math.max(1.4, text.split(/\s+/).length / 2.2);
  await handleUserText(text, 0.86, approxDuration, 0);
}

async function reviseLastTurn() {
  const text = els.manualText.value.trim() || state.lastUserText;
  if (!state.sessionId || !text) {
    return;
  }
  const data = await api("/api/revise", { sessionId: state.sessionId, text });
  els.liveLine.textContent = "已修正上一句文本并重新计算意图与纠错。";
  els.intent.textContent = data.intent;
  renderList(els.corrections, data.corrections || [], (item) => `${item.corrected} (${item.reason})`);
  renderList(els.tips, data.expressionTips || [], (item) => item);
  els.overallScore.textContent = data.scores.overall;
  els.grammarScore.textContent = data.scores.grammar;
}

async function generateSummary() {
  if (!state.sessionId) {
    return;
  }
  const data = await api("/api/summary", { sessionId: state.sessionId });
  const slotRows = Object.entries(data.filledSlots || {})
    .map(([key, value]) => `<li>${key}: ${value}</li>`)
    .join("");
  els.summary.innerHTML = `
    <div class="summary-card">
      <strong>${data.scenario} · ${data.turns} turns · ${data.durationSec}s</strong>
      <p>综合 ${data.scores.overall}，优势是${data.strongest}，下一步聚焦${data.focus}。</p>
      <p>场景完成度 ${Math.round(data.slotCompletion * 100)}%，纠错 ${data.correctionCount} 处，平均后端延迟 ${data.averageLatencyMs} ms。</p>
      <p>最近练习综合分变化：${data.progressDelta >= 0 ? "+" : ""}${data.progressDelta}</p>
    </div>
    <div class="summary-card">
      <strong>已完成任务点</strong>
      <ul>${slotRows || "<li>暂无</li>"}</ul>
    </div>
    <div class="summary-card">
      <strong>训练建议</strong>
      <ul>${data.nextDrills.map((item) => `<li>${item}</li>`).join("")}</ul>
    </div>
  `;
}

async function deleteUserData() {
  await api("/api/delete-user-data", { userId: state.userId });
  state.sessionId = null;
  els.messages.innerHTML = "";
  els.summary.innerHTML = "";
  resetFeedback();
  els.summaryBtn.disabled = true;
  els.reviseBtn.disabled = true;
  els.sendTextBtn.disabled = true;
  els.liveLine.textContent = "已删除本地会话与学习进度。";
}

els.startBtn.addEventListener("click", () => {
  startPractice().catch((error) => {
    els.liveLine.textContent = error.message;
  });
});

els.micBtn.addEventListener("click", () => {
  if (state.listening) {
    stopListening();
  } else {
    startListening();
  }
});

els.sendTextBtn.addEventListener("click", () => {
  sendManualText().catch((error) => {
    els.liveLine.textContent = error.message;
  });
});

els.manualText.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    sendManualText().catch((error) => {
      els.liveLine.textContent = error.message;
    });
  }
});

els.reviseBtn.addEventListener("click", () => {
  reviseLastTurn().catch((error) => {
    els.liveLine.textContent = error.message;
  });
});

els.summaryBtn.addEventListener("click", () => {
  generateSummary().catch((error) => {
    els.summary.textContent = error.message;
  });
});

els.deleteDataBtn.addEventListener("click", () => {
  deleteUserData().catch((error) => {
    els.liveLine.textContent = error.message;
  });
});

configureRecognition();
if (supportsSpeech()) {
  els.engineStatus.textContent = "语音模式";
}
