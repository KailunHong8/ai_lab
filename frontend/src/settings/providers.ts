// One provider/model catalog shared by the assistant, source extraction, and strategy parsing.

export type Provider = "router" | "bedrock" | "ollama" | "ollama-cloud";

export const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];
export const OLLAMA_CLOUD_MODELS = ["gpt-oss:120b", "gemma4:31b"];

// Resolution order when a saved configuration is unavailable.
export const PROVIDER_ORDER: Provider[] = ["router", "ollama-cloud", "ollama", "bedrock"];

export const PROVIDER_LABEL: Record<Provider, string> = {
  router: "AI Router",
  bedrock: "Bedrock (legacy)",
  ollama: "Ollama",
  "ollama-cloud": "Ollama Cloud",
};

export interface ProviderSettingsState {
  provider: Provider;
  model: string;
}

export function providerSummary(state: ProviderSettingsState): string {
  return state.model ? `${PROVIDER_LABEL[state.provider]} · ${state.model}` : PROVIDER_LABEL[state.provider];
}

export type ProviderCatalog = Record<Provider, string[]>;
export type ProviderAvailability = Record<Provider, boolean>;

const STORAGE_KEY = "quant.providerSettings";
const DEFAULT_STATE: ProviderSettingsState = { provider: "router", model: "" };

// Stored preferences are a convenience, not authoritative — they can be stale or absent.
export function readStoredSettings(): ProviderSettingsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed = JSON.parse(raw) as Partial<ProviderSettingsState>;
    if (!parsed.provider || !(parsed.provider in PROVIDER_LABEL)) return DEFAULT_STATE;
    return { provider: parsed.provider, model: parsed.model ?? "" };
  } catch {
    return DEFAULT_STATE;
  }
}

export function storeSettings(state: ProviderSettingsState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage can be unavailable — settings still work for this session */
  }
}

export interface ResolvedSelection extends ProviderSettingsState {
  notice: string;
}

// A saved provider/model is only kept when it is still verified available.
export function resolveSelection(
  saved: ProviderSettingsState,
  catalog: ProviderCatalog,
  availability: ProviderAvailability,
): ResolvedSelection {
  if (availability[saved.provider] && catalog[saved.provider].length > 0) {
    if (catalog[saved.provider].includes(saved.model)) {
      return { ...saved, notice: "" };
    }
    const fallback = catalog[saved.provider][0];
    return {
      provider: saved.provider,
      model: fallback,
      notice: saved.model
        ? `Saved model “${saved.model}” is unavailable on ${PROVIDER_LABEL[saved.provider]}. Using ${fallback}.`
        : "",
    };
  }

  const next = PROVIDER_ORDER.find((p) => availability[p] && catalog[p].length > 0);
  if (!next) {
    return { provider: "router", model: "", notice: "No AI provider is configured on the server. Check settings before sending." };
  }
  return {
    provider: next,
    model: catalog[next][0],
    notice: `Saved provider “${PROVIDER_LABEL[saved.provider]}” is unavailable. Using ${PROVIDER_LABEL[next]}.`,
  };
}
