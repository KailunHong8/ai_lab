# Change Spec - Embedded ChatGPT Go Split-Pane Integration & Perplexity Deactivation

**Date:** 2026-08-01  
**Status:** Proposed  
**Owner:** Quant App  
**Scope:** Frontend (React) UI, Backend & Start-up Configurations  

---

## 1) Problem Statement

The user's Perplexity Pro subscription has expired, disabling the underlying `perplexity-scrape` docker container proxy and causing research endpoints in the app to return 502/504 errors. However, the user has a 6-month **ChatGPT Go** subscription. 

Because ChatGPT is heavily protected by Cloudflare WAF, TLS JA4 fingerprinting, and security cookies, headless server-side scraping is extremely unstable and prone to frequent blocks. However, since the user runs and views the Quant app locally in **Google Chrome**, we can bypass these limitations by **directly embedding the live ChatGPT Go website inside the Quant App using a split-pane layout**.

We must also gracefully **disable the Perplexity Pro scraper proxy** across the start-up stack and the frontend interface, without deleting the code, so that if the user re-purchases Perplexity Pro in the future, it can be re-enabled with a single toggle.

---

## 2) Goals

1. **Provide a Built-in ChatGPT Interface:** Create a split-pane view in the app so that the user can query and browse ChatGPT Go side-by-side with Quant’s analytical tools without opening separate tabs.
2. **Disable Perplexity Container & Services:** Gracefully turn off the `perplexity-scrape` container and its health checks during startup, and hide (but preserve) Perplexity research buttons in the frontend UI.
3. **Automate Ticker Prompt Seeding:** Automatically generate a tailored, copyable or pre-filled deep-research prompt for single tickers and pass it directly to the embedded ChatGPT Go workspace via URL queries.
4. **Seamless Ingestion (Copy-Paste Dropzone):** Build a dedicated paste dropzone that takes the research response from ChatGPT, extracts citations/links, and uploads it to the database for thesis extraction and semantic retrieval.
5. **Optional Userscript Sync Bridge:** Document and provide a custom browser Tampermonkey script that adds a "Send to Quant" button inside the embedded ChatGPT frame to automatically synchronize answers with 1-click.

---

## 3) Non-Goals

1. **Autonomous Server-Side ChatGPT Scraping:** We will not run headless Playwright/Puppeteer automation or attempt to log in programmatically, which violates terms of service and triggers Cloudflare blocks.
2. **Deleting Perplexity Code:** We will not purge Perplexity models, client services, or router lines from the backend repository so that we can easily toggle it back on.

---

## 4) Browser Security & the Iframe Restriction

By default, loading `https://chatgpt.com` inside a standard React `<iframe>` fails because OpenAI sets the `X-Frame-Options: DENY` header and uses strict `Content-Security-Policy` rules to block iframe embedding.

Because this is a local desktop trading application running on `localhost:5173`, the user can easily bypass this browser restriction:
1. Install a free developer Chrome extension such as [Ignore X-Frame-Options](https://chromewebstore.google.com/detail/ignore-x-frame-options/ammcjofgjnidafidbbaidgpfegajnjee) or [Header Editor](https://github.com/suzp/HeaderEditor).
2. Configure the extension to strip the `X-Frame-Options` and `Content-Security-Policy` headers *only* for the `localhost` origin.
3. This allows the Quant App to render the fully functional, authenticated ChatGPT Go page natively in the iframe, using the user's active Chrome cookie session.

---

## 5) Architecture & Implementation Plan

### A) Disabling the Perplexity Pro Scraper Gracefully

To suspend Perplexity without removing the underlying support:

1. **Environment Config (`.env`):**
   Add a new environment flag to indicate whether Perplexity is disabled:
   ```env
   DISABLE_PERPLEXITY=true
   ```

2. **Start-up Stack Configuration (`scripts/start_dev_stack.sh`):**
   Update the start-up script to check the `DISABLE_PERPLEXITY` flag before executing container setup or health checks:
   ```bash
   start_perplexity() {
     # Read from .env
     local disable_val
     disable_val="$(dotenv_get DISABLE_PERPLEXITY "false")"
     if [[ "$disable_val" == "true" ]]; then
       echo "[perplexity] disabled via .env; skipping scraper container launch and health check"
       return 0
     fi
     
     # ... rest of the legacy start_perplexity code ...
   }
   ```
   Also, conditionally output the startup log printouts if Perplexity is skipped.

3. **Frontend UI Adjustments (`frontend/src/pages/Research.tsx` and `Agent.tsx`):**
   - We will not remove the Perplexity ingestion form components or the AI Copilot "Research" button.
   - Instead, we will wrap them in conditional checks based on an environment variable or simply add a clean `disabled` overlay or status message so they are preserved but visually inactive.

---

### B) Building the Split-Pane ChatGPT UI

We will create a dual-panel layout on the **Research** page (or a new dedicated page `/research-chat`).

1. **Left Panel (Quant Research Tools):**
   - **Ticker Selector:** A text field where the user types a ticker (e.g., `AAPL`, `MSFT`).
   - **Prompt Copy Center:** Renders a list of pre-configured financial prompts. When a ticker is selected, it generates prompts like:
     - `"Search real-time: Analyze recent market sentiment, analyst ratings, and time-sensitive catalysts for {symbol}."`
     - `"What are the current supply chain challenges and competitive threats facing {symbol}?"`
   - **ChatGPT Ingestion Dropzone:** A text-area paste component where the user can paste ChatGPT's completed output.
   - **Save to Database Button:** A button that sends the pasted text, ticker symbol, and metadata to `/api/knowledge/upload` to index it semantically in ChromaDB and extract research theses.

2. **Right Panel (Live ChatGPT Go Iframe):**
   - An iframe pointing to `https://chatgpt.com`.
   - **Automated Prompt Seeding:** When the user types or selects a ticker in the Left Panel, the iframe’s source URL will dynamically update to:
     ```
     https://chatgpt.com/?q=Analyze+market+sentiment+for+{ticker}
     ```
     This triggers Chrome to automatically populate ChatGPT's text box with the search command, requiring the user to only hit "Enter" on their keyboard.

```
+------------------------------------------+------------------------------------------+
|            LEFT: QUANT PANEL             |          RIGHT: EMBEDDED CHATGPT         |
|                                          |                                          |
|  Ticker: [ AAPL ]                        |  [chatgpt.com]                           |
|                                          |                                          |
|  [Copy Sentiment Prompt] [Copy supply]   |  User: Analyze market sentiment for AAPL |
|                                          |                                          |
|  [ Paste ChatGPT Response Here ]         |  ChatGPT Go: Apple's market sentiment is |
|                                          |  currently bullish because...            |
|  [ Ingest into Quant App DB ]            |                                          |
+------------------------------------------+------------------------------------------+
```

---

### C) Ingestion Pipeline: Mapping ChatGPT to the Knowledge Database

When the user pastes the ChatGPT response into the Left Panel's Dropzone and clicks **Ingest**:

1. **Frontend Parsing:**
   The React page parses the pasted text. It uses regex to extract any citation links if present in the text (e.g., standard HTTP URLs) to populate the sources list.
2. **Unified API Call:**
   The frontend calls the existing `/api/knowledge/upload` endpoint:
   ```typescript
   uploadDocument({
     title: `[ChatGPT Go] Research: ${ticker}`,
     source: "ChatGPT",
     text: pastedText,
     document_type: "market_opinion" // Indexes as timely web research with 30-day TTL
   });
   ```
3. **Automatic Extraction:**
   The backend automatically treats the ingested text as a `market_opinion` document, stores it with a 30-day expiration, triggers the thesis extraction pipeline (using Bedrock/Ollama), and builds semantic vectors inside ChromaDB.

---

### D) Optional "Tampermonkey Bridge" for 1-Click Syncing

For users who want to skip manual copy-pasting, we will document a lightweight browser userscript.

1. **How it Intercepts:**
   The script watches the `chatgpt.com` page DOM for assistant messages (`[data-message-author-role="assistant"]`).
2. **How it Synchronizes:**
   It appends a styled **📤 Send to Quant App** button on each response. When clicked, it does a local cross-origin HTTP POST call to `http://localhost:8000/api/knowledge/upload` to automatically push the text and parsed citations straight into the Quant DB.

---

## 6) Step-by-Step Transition Plan

```text
1. Edit .env & start_dev_stack.sh to support DISABLE_PERPLEXITY toggle
2. Build Split-Pane Integrated Iframe Layout inside Research page
3. Hide legacy Perplexity Deep Research form buttons under inactive states
4. Integrate Prompt Seeding and Clipboard Paste Dropzone
5. Add documentation/setup steps in the UI for the Chrome Extension and Tampermonkey script
```

---

## 7) Validation & Exit Criteria

1. **Verify Startup:** Starting the developer stack with `DISABLE_PERPLEXITY=true` launches the backend and frontend, but skips starting the `perplexity` scraping docker container and displays no related health-check failures.
2. **Verify Split-Pane Iframe:** Navigating to the **Research** tab shows a side-by-side split screen. On the right, ChatGPT Go loads successfully (provided the browser extension is active).
3. **Verify Prompt Copying:** Selecting a ticker dynamically updates the copyable prompt text and changes the iframe query string.
4. **Verify Manual Ingestion:** Pasting a ChatGPT output into the Left Panel's dropzone and clicking "Ingest" successfully uploads, runs thesis extraction, and builds semantic vectors in ChromaDB (confirm via `/api/knowledge/documents` list).
5. **Verify Reversibility:** Toggling `DISABLE_PERPLEXITY=false` and restarting the stack launches the scraper proxy container exactly as before.
