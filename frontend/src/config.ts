// App-wide feature flags.
//
// Perplexity Pro is disabled by default (subscription expired) — the embedded
// ChatGPT Go pane replaces it. To re-enable the Perplexity research UI, set
// VITE_DISABLE_PERPLEXITY=false in frontend/.env (and DISABLE_PERPLEXITY=false
// in the root .env so the scraper container starts back up).
export const PERPLEXITY_DISABLED =
  (import.meta.env.VITE_DISABLE_PERPLEXITY ?? "true").toString().toLowerCase() !== "false";
