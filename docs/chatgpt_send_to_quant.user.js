// ==UserScript==
// @name         Send ChatGPT Answer to Quant App
// @namespace    quant-app
// @version      1.0
// @description  Adds a "📤 Send to Quant" button under each ChatGPT assistant reply that pushes the text (and any citation links) into the local Quant knowledge base.
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function () {
  "use strict";

  const QUANT_ENDPOINT = "http://localhost:8000/api/knowledge/ingest-chatgpt";

  // Try to infer a ticker from the surrounding conversation (first 1–5 uppercase token).
  function guessTicker(text) {
    const m = text.match(/\b[A-Z]{1,5}\b/);
    return m ? m[0] : "";
  }

  function post(text, button) {
    const original = button.textContent;
    button.textContent = "Sending…";
    button.disabled = true;

    GM_xmlhttpRequest({
      method: "POST",
      url: QUANT_ENDPOINT,
      headers: { "Content-Type": "application/json" },
      data: JSON.stringify({ text: text, ticker: guessTicker(text) }),
      onload: function (res) {
        let ok = res.status >= 200 && res.status < 300;
        let label = "❌ Failed";
        if (ok) {
          try {
            const body = JSON.parse(res.responseText);
            label = body.status === "duplicate" ? "✓ Already saved" : "✓ Sent to Quant";
          } catch (e) {
            label = "✓ Sent to Quant";
          }
        }
        button.textContent = label;
        setTimeout(() => {
          button.textContent = original;
          button.disabled = false;
        }, 2500);
      },
      onerror: function () {
        button.textContent = "❌ Failed (is Quant running?)";
        setTimeout(() => {
          button.textContent = original;
          button.disabled = false;
        }, 2500);
      },
    });
  }

  function decorate(node) {
    if (node.dataset.quantDecorated) return;
    node.dataset.quantDecorated = "1";

    const btn = document.createElement("button");
    btn.textContent = "📤 Send to Quant";
    btn.style.cssText =
      "margin-top:8px;padding:4px 10px;font-size:12px;border-radius:6px;" +
      "border:1px solid #6366f1;background:#eef2ff;color:#4338ca;cursor:pointer;";
    btn.addEventListener("click", function () {
      post(node.innerText || node.textContent || "", btn);
    });
    node.appendChild(btn);
  }

  function scan() {
    document
      .querySelectorAll('[data-message-author-role="assistant"]')
      .forEach(decorate);
  }

  // ChatGPT streams answers into the DOM, so re-scan on mutations.
  const observer = new MutationObserver(() => scan());
  observer.observe(document.body, { childList: true, subtree: true });
  scan();
})();
