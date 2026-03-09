/**
 * Melvin God Mode — Chat JavaScript
 * Handles Socket.IO connection, message sending/receiving, and UI updates.
 */

(function () {
  "use strict";

  /* ── State ──────────────────────────────────────────────── */
  let socket = null;
  let isStreaming = false;
  let streamingBubble = null;
  let streamBuffer = "";
  const MAX_HISTORY = 40;

  /* ── DOM refs ───────────────────────────────────────────── */
  const messagesEl   = document.getElementById("chat-messages");
  const inputEl      = document.getElementById("chat-input");
  const sendBtn      = document.getElementById("send-btn");
  const modelSelect  = document.getElementById("model-select");
  const clearBtn     = document.getElementById("clear-btn");
  const statusDot    = document.getElementById("socket-status");
  const statusText   = document.getElementById("socket-status-text");
  const charCounter  = document.getElementById("char-counter");

  /* ── History (sessionStorage) ───────────────────────────── */
  function loadHistory() {
    try {
      return JSON.parse(sessionStorage.getItem("melvin_chat_history") || "[]");
    } catch {
      return [];
    }
  }

  function saveHistory(history) {
    try {
      const trimmed = history.slice(-MAX_HISTORY);
      sessionStorage.setItem("melvin_chat_history", JSON.stringify(trimmed));
    } catch {}
  }

  function addToHistory(role, content) {
    const history = loadHistory();
    history.push({ role, content });
    saveHistory(history);
  }

  /* ── Socket.IO ──────────────────────────────────────────── */
  function initSocket() {
    socket = io({ transports: ["websocket", "polling"] });

    socket.on("connect", () => {
      setStatus("online", "Connected");
    });

    socket.on("disconnect", () => {
      setStatus("offline", "Disconnected");
    });

    socket.on("connect_error", () => {
      setStatus("offline", "Connection error");
    });

    socket.on("status", (data) => {
      setStatus("online", "Connected");
    });

    socket.on("chat_start", (data) => {
      isStreaming = true;
      streamBuffer = "";
      streamingBubble = createStreamingBubble();
      setSending(true);
    });

    socket.on("chat_token", (data) => {
      if (!streamingBubble) return;
      streamBuffer += data.token;
      const contentEl = streamingBubble.querySelector(".bubble-content");
      if (contentEl) {
        contentEl.textContent = streamBuffer;
        scrollToBottom();
      }
    });

    socket.on("chat_done", (data) => {
      if (streamingBubble) {
        finaliseStreamingBubble(streamingBubble, streamBuffer, data.model);
        addToHistory("assistant", streamBuffer);
        streamingBubble = null;
      }
      isStreaming = false;
      setSending(false);
      scrollToBottom();
    });

    socket.on("chat_error", (data) => {
      if (streamingBubble) {
        streamingBubble.remove();
        streamingBubble = null;
      }
      isStreaming = false;
      setSending(false);
      showToast(data.error || "An error occurred.", "error");
    });
  }

  /* ── UI helpers ─────────────────────────────────────────── */
  function setStatus(state, label) {
    if (statusDot)  { statusDot.className = "status-dot" + (state === "offline" ? " offline" : ""); }
    if (statusText) { statusText.textContent = label; }
  }

  function setSending(sending) {
    if (sendBtn) { sendBtn.disabled = sending; }
    if (inputEl) { inputEl.disabled = sending; }
    if (sendBtn) {
      sendBtn.innerHTML = sending
        ? '<span class="spinner"></span>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';
    }
  }

  function scrollToBottom() {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function hideEmptyState() {
    const empty = document.getElementById("chat-empty");
    if (empty) empty.style.display = "none";
  }

  /* ── Message rendering ──────────────────────────────────── */
  function createMessage(role, content, model) {
    hideEmptyState();
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "U" : "AI";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const contentEl = document.createElement("span");
    contentEl.className = "bubble-content";
    contentEl.textContent = content;

    const meta = document.createElement("span");
    meta.className = "message-time";
    meta.textContent = nowTime() + (model && role === "assistant" ? `  ·  ${model}` : "");

    bubble.appendChild(contentEl);
    bubble.appendChild(meta);
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function createStreamingBubble() {
    hideEmptyState();
    const wrap = document.createElement("div");
    wrap.className = "message assistant";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "AI";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const contentEl = document.createElement("span");
    contentEl.className = "bubble-content cursor-blink";

    bubble.appendChild(contentEl);
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function finaliseStreamingBubble(wrap, fullContent, model) {
    const contentEl = wrap.querySelector(".bubble-content");
    if (contentEl) {
      contentEl.className = "bubble-content"; // remove cursor-blink
      contentEl.textContent = fullContent;
    }
    const bubble = wrap.querySelector(".message-bubble");
    if (bubble) {
      const meta = document.createElement("span");
      meta.className = "message-time";
      meta.textContent = nowTime() + (model ? `  ·  ${model}` : "");
      bubble.appendChild(meta);
    }
  }

  /* ── Send ───────────────────────────────────────────────── */
  function sendMessage() {
    if (!inputEl) return;
    const text = inputEl.value.trim();
    if (!text || isStreaming) return;

    const model = modelSelect ? modelSelect.value : "llama3";
    const history = loadHistory();

    createMessage("user", text, null);
    addToHistory("user", text);
    inputEl.value = "";
    updateCharCounter();
    inputEl.style.height = "44px";

    socket.emit("chat_message", { model, message: text, history });
  }

  /* ── Event listeners ────────────────────────────────────── */
  if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
  }

  if (inputEl) {
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    inputEl.addEventListener("input", () => {
      // Auto-grow textarea
      inputEl.style.height = "44px";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
      updateCharCounter();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      sessionStorage.removeItem("melvin_chat_history");
      if (messagesEl) {
        messagesEl.innerHTML =
          '<div class="chat-empty" id="chat-empty">' +
          '<pre class="ascii-logo">MELVIN // GOD MODE</pre>' +
          '<p class="text-dim">Start a conversation. Select a model above.</p>' +
          '</div>';
      }
    });
  }

  /* ── Model loading ──────────────────────────────────────── */
  function loadModels() {
    if (!modelSelect) return;
    fetch("/api/models")
      .then((r) => r.json())
      .then((data) => {
        const models = (data.models || []).map((m) => m.name).filter(Boolean);
        const current = modelSelect.value;
        modelSelect.innerHTML = "";
        if (models.length === 0) {
          const opt = document.createElement("option");
          opt.value = "llama3";
          opt.textContent = "llama3 (default)";
          modelSelect.appendChild(opt);
        } else {
          models.forEach((name) => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            if (name === current) opt.selected = true;
            modelSelect.appendChild(opt);
          });
        }
      })
      .catch(() => {}); // Silently fail — Ollama may not be running
  }

  /* ── Char counter ───────────────────────────────────────── */
  function updateCharCounter() {
    if (!charCounter || !inputEl) return;
    const len = inputEl.value.length;
    charCounter.textContent = len > 0 ? `${len} chars` : "";
  }

  /* ── Toast helper ───────────────────────────────────────── */
  function showToast(msg, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      document.body.appendChild(container);
    }
    const icons = { success: "✓", error: "✗", info: "ℹ" };
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${icons[type] || "ℹ"}</span>
      <span class="toast-msg">${msg}</span>
      <button class="toast-close" onclick="this.parentElement.remove()">×</button>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  /* ── Restore history on page load ───────────────────────── */
  function restoreHistory() {
    const history = loadHistory();
    if (history.length === 0) return;
    hideEmptyState();
    const lastModel = modelSelect ? modelSelect.value : "llama3";
    history.forEach((entry) => {
      createMessage(entry.role, entry.content, entry.role === "assistant" ? lastModel : null);
    });
  }

  /* ── Init ───────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", () => {
    loadModels();
    initSocket();
    restoreHistory();
    if (inputEl) inputEl.focus();
  });

  // Expose for any inline handlers
  window.sendMessage = sendMessage;
})();
