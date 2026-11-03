// CYBERAI 2.0 — offline-only mode.
// This file deliberately makes no network requests and never calls the paid AI API.
(() => {
  const localAnswer = window.getAnswer;

  window.getAnswer = function (message) {
    return localAnswer(message);
  };

  window.configureAIConnection = function () {
    alert("CYBERAI is currently running in offline knowledge-library mode. No API connection is used.");
  };

  function showOfflineStatus() {
    const status = document.getElementById("aiConnectionStatus");
    if (status) status.textContent = "Offline knowledge-library mode is active. No API requests or paid AI credits are used.";
  }

  document.addEventListener("DOMContentLoaded", showOfflineStatus);
  showOfflineStatus();
})();
