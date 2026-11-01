// CYBERAI 2.0 browser-side connection. The API key never belongs in this file.
(() => {
  const API_URL_KEY = "cyberai_ai_endpoint";
  const getEndpoint = () => (localStorage.getItem(API_URL_KEY) || "").trim();

  window.configureAIConnection = function () {
    const current = getEndpoint();
    const value = prompt(
      "Paste the public URL of your deployed CYBERAI Cloudflare Worker, ending in /api/chat.\nDo not paste an API key here.",
      current
    );
    if (value === null) return;
    const endpoint = value.trim();
    if (!endpoint) {
      localStorage.removeItem(API_URL_KEY);
      updateStatus();
      alert("AI connection URL cleared. The local knowledge library remains available.");
      return;
    }
    try {
      const parsed = new URL(endpoint);
      if (parsed.protocol !== "https:" || !parsed.pathname.endsWith("/api/chat")) {
        throw new Error("Use an HTTPS Worker URL ending in /api/chat.");
      }
      localStorage.setItem(API_URL_KEY, endpoint);
      updateStatus();
      alert("Worker URL saved. CYBERAI will test the connection when you send your next message.");
    } catch (error) {
      alert(error.message || "Please enter a valid HTTPS Worker URL ending in /api/chat.");
    }
  };

  function updateStatus() {
    const el = document.getElementById("aiConnectionStatus");
    if (!el) return;
    el.textContent = getEndpoint()
      ? "AI backend URL saved. API key is stored separately on the server."
      : "AI backend not connected yet. Local knowledge remains available.";
  }

  const originalGetAnswer = window.getAnswer;
  window.getAnswer = async function (text) {
    const endpoint = getEndpoint();
    if (!endpoint) return originalGetAnswer(text);

    const history = (window.currentMessages || []).slice(-11, -1).map(item => ({
      role: item.role === "bot" ? "assistant" : "user",
      content: item.text
    }));

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "AI connection failed (" + response.status + ").");
      if (!data.answer) throw new Error("The AI service returned no answer.");
      return data.answer;
    } catch (error) {
      return "I couldn't reach the live AI service: " + error.message +
        "\n\nYour local knowledge library is still available. Check the Worker URL and server setup.";
    }
  };

  window.sendMessage = async function () {
    const input = document.getElementById("messageInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    window.addUserMessage(text);
    const button = document.querySelector('button[onclick="sendMessage()"]');
    if (button) button.disabled = true;
    try {
      const answer = await window.getAnswer(text);
      window.addBotMessage(answer);
    } finally {
      if (button) button.disabled = false;
    }
  };

  // Route spoken call messages through the same live AI endpoint.
  window.beginCallListening = function () {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      document.getElementById("callInfo").textContent =
        "Speech recognition is unavailable. Use the chat microphone button instead.";
      return;
    }
    if (!window.callActive || window.muted || window.recognitionActive) return;
    window.recognition = new SpeechRecognition();
    window.recognition.lang = "en-NG";
    window.recognition.interimResults = false;
    window.recognition.continuous = false;
    window.recognition.onstart = () => {
      window.recognitionActive = true;
      document.getElementById("callInfo").textContent = "Listening to you...";
    };
    window.recognition.onresult = async event => {
      const spokenText = event.results[0][0].transcript;
      window.addUserMessage(spokenText);
      document.getElementById("callInfo").textContent = "Thinking...";
      const answer = await window.getAnswer(spokenText);
      window.addBotMessage(answer);
      document.getElementById("callInfo").textContent = "You said: " + spokenText;
    };
    window.recognition.onerror = event => {
      document.getElementById("callInfo").textContent = "Listening issue: " + event.error + ".";
    };
    window.recognition.onend = () => {
      window.recognitionActive = false;
      if (window.callActive && !window.muted) setTimeout(window.beginCallListening, 700);
    };
    try { window.recognition.start(); } catch { window.recognitionActive = false; }
  };

  document.addEventListener("DOMContentLoaded", updateStatus);
  setTimeout(updateStatus, 0);
})();
