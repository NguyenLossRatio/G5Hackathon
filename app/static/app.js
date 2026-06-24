const state = {
  sessionId: null,
  phase: "start",
  actions: [],
  busy: false,
};

const elements = {
  messages: document.querySelector("#messages"),
  phaseLabel: document.querySelector("#phase-label"),
  questionCounter: document.querySelector("#question-counter"),
  status: document.querySelector("#status-message"),
  sampleButton: document.querySelector("#sample-w2-button"),
  uploadInput: document.querySelector("#w2-upload"),
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  downloadLink: document.querySelector("#download-link"),
  events: document.querySelector("#events"),
  groups: {
    w2: document.querySelector("#w2-actions"),
    filingStatus: document.querySelector("#filing-status-actions"),
    digitalAssets: document.querySelector("#digital-assets-actions"),
    refund: document.querySelector("#refund-actions"),
  },
};

const phaseLabels = {
  start: "Starting session",
  need_w2: "W-2 intake",
  need_filing_status: "Filing status",
  need_household: "Household details",
  need_digital_assets: "Digital assets",
  need_refund: "Refund method",
  complete: "Complete",
};

document.addEventListener("DOMContentLoaded", startChat);

elements.sampleButton?.addEventListener("click", async () => {
  if (!canSendRequest()) {
    return;
  }
  appendMessage("user", "Use sample W-2");
  await uploadW2({ useSample: true });
});

elements.uploadInput?.addEventListener("change", async () => {
  const file = elements.uploadInput.files?.[0];
  if (!file || !canSendRequest()) {
    return;
  }
  appendMessage("user", `Upload ${file.name}`);
  await uploadW2({ file });
  elements.uploadInput.value = "";
});

document.querySelectorAll("[data-answer]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!canSendRequest()) {
      return;
    }
    const rawAnswer = button.dataset.answer;
    const answer = answerValue(rawAnswer);
    appendMessage("user", button.textContent.trim());
    await sendAnswer(answer);
  });
});

elements.chatForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!canSendRequest()) {
    return;
  }
  const value = elements.messageInput.value.trim();
  if (!value) {
    return;
  }
  appendMessage("user", value);
  elements.messageInput.value = "";
  if (state.phase === "need_refund") {
    await sendAnswer(refundTextAnswer(value));
  } else if (state.actions.includes("answer_household")) {
    await sendAnswer(value);
  } else {
    await sendMessage(value);
  }
});

async function startChat() {
  setBusy(true, "Starting chat...");
  try {
    const response = await api("/api/chat/start", { method: "POST" });
    handleChatResponse(response);
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

function canSendRequest() {
  return Boolean(state.sessionId) && !state.busy;
}

async function uploadW2({ useSample = false, file = null }) {
  setBusy(true, "Reading W-2...");
  try {
    const body = new FormData();
    body.append("session_id", state.sessionId);
    if (useSample) {
      body.append("use_sample", "true");
    } else {
      body.append("file", file);
    }
    const response = await api("/api/chat/upload-w2", { method: "POST", body });
    handleChatResponse(response);
  } catch (error) {
    showError(error);
    await refreshEvents();
  } finally {
    setBusy(false);
  }
}

async function sendAnswer(answer) {
  setBusy(true, "Sending answer...");
  try {
    const response = await api("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, answer }),
    });
    handleChatResponse(response);
  } catch (error) {
    showError(error);
    await refreshEvents();
  } finally {
    setBusy(false);
  }
}

async function sendMessage(message) {
  setBusy(true, "Sending message...");
  try {
    const response = await api("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message }),
    });
    handleChatResponse(response);
  } catch (error) {
    showError(error);
    await refreshEvents();
  } finally {
    setBusy(false);
  }
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status if the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function handleChatResponse(response) {
  state.sessionId = response.session_id;
  state.phase = response.phase;
  state.actions = response.actions || [];
  appendMessage("assistant", response.message);
  renderState(response);
  refreshEvents();
}

function renderState(response) {
  elements.phaseLabel.textContent = phaseLabels[response.phase] || response.phase;
  elements.questionCounter.textContent = `Question ${response.question_count || 0} of 5`;
  elements.downloadLink.hidden = !response.download_url;
  if (response.download_url) {
    elements.downloadLink.href = response.download_url;
  }

  setGroupVisibility(elements.groups.w2, hasAnyAction(["upload_w2", "use_sample_w2"]));
  setGroupVisibility(elements.groups.filingStatus, hasAnyAction([
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
  ]));
  setGroupVisibility(elements.groups.digitalAssets, hasAnyAction(["yes", "no"]));
  setGroupVisibility(elements.groups.refund, hasAnyAction(["paper_check", "direct_deposit"]));

  const showTextInput = state.actions.includes("answer_household")
    || state.phase === "need_refund"
    || !response.actions?.length;
  elements.chatForm.hidden = response.phase === "complete" || !showTextInput;
  if (state.actions.includes("answer_household")) {
    elements.messageInput.placeholder = "Type household details";
  } else if (state.phase === "need_refund") {
    elements.messageInput.placeholder = "Type paper check or fake direct deposit details";
  } else {
    elements.messageInput.placeholder = "Message";
  }
}

function setGroupVisibility(group, visible) {
  if (group) {
    group.hidden = !visible;
  }
}

function hasAnyAction(actions) {
  return actions.some((action) => state.actions.includes(action));
}

function answerValue(rawAnswer) {
  if (rawAnswer === "true") {
    return true;
  }
  if (rawAnswer === "false") {
    return false;
  }
  if (rawAnswer === "direct_deposit") {
    return fakeDirectDepositAnswer();
  }
  return rawAnswer;
}

function refundTextAnswer(value) {
  const normalized = value.toLowerCase();
  if (normalized.includes("direct deposit") || normalized.includes("routing") || normalized.includes("account")) {
    return fakeDirectDepositAnswer();
  }
  if (normalized.includes("paper") || normalized.includes("check")) {
    return "paper_check";
  }
  return value;
}

function fakeDirectDepositAnswer() {
  return {
    method: "direct_deposit",
    routing_number: "000000000",
    account_number: "000000000000",
    account_type: "checking",
  };
}

function appendMessage(role, text) {
  if (!text) {
    return;
  }
  const message = document.createElement("article");
  message.className = `message ${role}`;
  message.textContent = text;
  elements.messages.append(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function refreshEvents() {
  if (!state.sessionId) {
    return;
  }
  try {
    const response = await fetch(`/api/sessions/${state.sessionId}/events`);
    if (!response.ok) {
      return;
    }
    const body = await response.json();
    renderEvents(body.events || []);
  } catch {
    // Observation refresh should not block the chat flow.
  }
}

function renderEvents(events) {
  elements.events.replaceChildren();
  for (const event of events) {
    const item = document.createElement("li");
    const type = document.createElement("strong");
    const payload = document.createElement("code");
    type.textContent = event.event_type;
    payload.textContent = compactJson(sanitizePayload(event.payload || {}));
    item.append(type, payload);
    elements.events.append(item);
  }
}

function sanitizePayload(value) {
  if (Array.isArray(value)) {
    return value.map(sanitizePayload);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .map(([key, nested]) => [
          key,
          shouldRedactPayloadKey(key) ? redactPathValue(nested) : sanitizePayload(nested),
        ])
    );
  }
  if (typeof value === "string") {
    return redactLocalPaths(value);
  }
  return value;
}

function shouldRedactPayloadKey(key) {
  const normalized = key.toLowerCase();
  return normalized === "path"
    || normalized.endsWith("_path")
    || normalized.endsWith("_dir")
    || normalized.endsWith("_file");
}

function redactPathValue(value) {
  if (typeof value === "string") {
    const redacted = redactLocalPaths(value);
    return redacted === value ? "[local path hidden]" : redacted;
  }
  return "[local path hidden]";
}

function redactLocalPaths(value) {
  return value.replace(localPathPattern(), "[local path hidden]");
}

function looksLikeLocalPath(value) {
  return localPathPattern().test(value);
}

function localPathPattern() {
  return /(file:\/\/\/[^\s"',;)}\]]+|(?:~|\/Users|\/tmp|\/private\/tmp|\/var|\/private\/var)(?:\/[^\s"',;)}\]]*)*|[A-Za-z]:\\[^\s"',;)}\]]+)/g;
}

function compactJson(value) {
  return JSON.stringify(value);
}

function setBusy(isBusy, message = "") {
  state.busy = isBusy;
  elements.status.textContent = message;
  document.querySelectorAll("button, input").forEach((control) => {
    control.disabled = isBusy;
  });
}

function showError(error) {
  elements.status.textContent = error.message || "Something went wrong.";
}

globalThis.__taxAssistantTestHooks = {
  state,
  canSendRequest,
  refundTextAnswer,
  fakeDirectDepositAnswer,
  sanitizePayload,
  shouldRedactPayloadKey,
  looksLikeLocalPath,
};
