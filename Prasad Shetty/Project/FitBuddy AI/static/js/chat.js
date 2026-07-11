/**
 * static/js/chat.js
 * FitBuddy AI – AI Chat page logic
 *
 * Communicates exclusively with the Flask /api/chat endpoint.
 * Displays source badge (watsonx Orchestrate / watsonx.ai / fallback).
 * No credentials or API keys are present here.
 */

/* ── Source badge labels ──────────────────────────────────────────────────── */
const SOURCE_LABELS = {
  orchestrate: { text: 'IBM watsonx Orchestrate', color: '#2563eb' },
  watsonx_ai:  { text: 'IBM watsonx.ai',          color: '#7c3aed' },
  fallback:    { text: 'Built-in Knowledge',       color: '#57606a' },
};

/* ── Textarea auto-resize ─────────────────────────────────────────────────── */
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

document.getElementById('chatInput').addEventListener('input', function () {
  autoResize(this);
});

/* ── Enter to send (Shift+Enter = newline) ────────────────────────────────── */
function handleChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

/* ── Fill input from sidebar prompt buttons ──────────────────────────────── */
function useSuggestedPrompt(btn) {
  const input = document.getElementById('chatInput');
  input.value = btn.dataset.prompt;
  autoResize(input);
  input.focus();
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function getTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Append a message bubble to the chat pane.
 * @param {'user'|'ai'} role
 * @param {string}      content    Plain text (newlines converted to <br>)
 * @param {string}      [source]   API source key – shown as a small badge on AI messages
 */
function addMessage(role, content, source) {
  const container = document.getElementById('chatMessages');
  const isUser    = role === 'user';
  const div       = document.createElement('div');
  div.className   = `message ${isUser ? 'user' : 'ai'} fade-in`;

  // Source badge for AI messages
  let sourceBadge = '';
  if (!isUser && source && SOURCE_LABELS[source]) {
    const { text, color } = SOURCE_LABELS[source];
    sourceBadge = `<span style="font-size:.65rem;color:${color};font-weight:600;opacity:.8;">`
                + `<i class="bi bi-cpu me-1"></i>${text}</span>`;
  }

  div.innerHTML = `
    <div class="message-avatar ${isUser ? 'user-avatar' : 'ai-avatar'}">
      <i class="bi bi-${isUser ? 'person-fill' : 'robot'}"></i>
    </div>
    <div>
      <div class="message-bubble">${content.replace(/\n/g, '<br>')}</div>
      <div class="message-time d-flex align-items-center gap-2">
        <span>${getTime()}</span>
        ${sourceBadge}
      </div>
    </div>`;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

/* ── Typing animation ────────────────────────────────────────────────────── */
function addTyping() {
  const container = document.getElementById('chatMessages');
  const div       = document.createElement('div');
  div.className   = 'message ai fade-in';
  div.id          = 'typingIndicator';
  div.innerHTML   = `
    <div class="message-avatar ai-avatar"><i class="bi bi-robot"></i></div>
    <div>
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      <div style="font-size:.65rem;color:var(--text-light);margin-top:4px;">
        <i class="bi bi-cpu me-1"></i>IBM watsonx is thinking…
      </div>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.remove();
}

/* ── Send message ─────────────────────────────────────────────────────────── */
async function sendMessage() {
  const input = document.getElementById('chatInput');
  const btn   = document.getElementById('sendBtn');
  const msg   = input.value.trim();
  if (!msg) return;

  addMessage('user', msg);
  input.value        = '';
  input.style.height = 'auto';
  btn.disabled       = true;
  addTyping();

  try {
    const res  = await fetch('/api/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: msg }),
    });

    const data = await res.json();
    removeTyping();

    if (!res.ok) {
      addMessage('ai', data.error || 'Something went wrong. Please try again.');
      return;
    }

    addMessage('ai', data.response || 'Sorry, I could not process your request.', data.source);

  } catch (err) {
    removeTyping();
    addMessage('ai', 'Network error — please check your connection and try again.');
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

/* ── Update header source label ─────────────────────────────────────────── */
function _updateSourceLabel(source) {
  const el = document.getElementById('aiSourceLabel');
  if (!el || !source) return;
  const info = SOURCE_LABELS[source];
  if (!info) return;
  el.innerHTML = `<i class="bi bi-cpu me-1" style="color:${info.color};"></i>`
               + `<span style="color:${info.color};">${info.text}</span>`;
}

/* ── Clear chat ──────────────────────────────────────────────────────────── */
async function clearChat() {
  try {
    await fetch('/api/chat/clear', { method: 'POST' });
  } catch (_) { /* ignore network errors on clear */ }

  const container = document.getElementById('chatMessages');
  container.innerHTML = '';
  addMessage('ai', 'Chat cleared! How can I help with your fitness journey today?', 'fallback');
}
