import { useEffect, useMemo, useState } from "react";
import { listOllamaModels, listRouterModels } from "../api/client";
import {
  BEDROCK_MODELS,
  OLLAMA_CLOUD_MODELS,
  PROVIDER_LABEL,
  type Provider,
  type ProviderAvailability,
  type ProviderCatalog,
  readStoredSettings,
  resolveSelection,
  storeSettings,
} from "./providers";

export interface ProviderSettingsApi {
  provider: Provider;
  model: string;
  catalog: ProviderCatalog;
  availability: ProviderAvailability;
  notice: string;
  loaded: boolean;
  changeProvider: (next: Provider) => void;
  changeModel: (next: string) => void;
}

const EMPTY_CATALOG: ProviderCatalog = {
  router: [],
  bedrock: BEDROCK_MODELS,
  ollama: [],
  "ollama-cloud": OLLAMA_CLOUD_MODELS,
};

const NO_PROVIDER: ProviderAvailability = {
  router: false,
  bedrock: true, // legacy path: configured server-side, not verifiable from the browser
  ollama: false,
  "ollama-cloud": false,
};

// Shared provider/model preference: verified on load, persisted for the next visit.
export function useProviderSettings(): ProviderSettingsApi {
  const saved = useMemo(() => readStoredSettings(), []);
  const [provider, setProvider] = useState<Provider>(saved.provider);
  const [model, setModel] = useState(saved.model);
  const [catalog, setCatalog] = useState<ProviderCatalog>(EMPTY_CATALOG);
  const [availability, setAvailability] = useState<ProviderAvailability>(NO_PROVIDER);
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([listRouterModels(), listOllamaModels()]).then(([routerResult, ollamaResult]) => {
      if (cancelled) return;

      const nextCatalog: ProviderCatalog = { ...EMPTY_CATALOG };
      const nextAvailability: ProviderAvailability = { ...NO_PROVIDER };

      if (routerResult.status === "fulfilled") {
        const data = routerResult.value as {
          models?: string[];
          available?: boolean;
          ollama_cloud_available?: boolean;
        };
        nextCatalog.router = data.models ?? [];
        nextAvailability.router = Boolean(data.available) && nextCatalog.router.length > 0;
        nextAvailability["ollama-cloud"] = Boolean(data.ollama_cloud_available);
      }
      if (ollamaResult.status === "fulfilled") {
        const data = ollamaResult.value as { models?: string[]; available?: boolean };
        nextCatalog.ollama = data.models ?? [];
        nextAvailability.ollama = Boolean(data.available) && nextCatalog.ollama.length > 0;
      }

      const resolved = resolveSelection(saved, nextCatalog, nextAvailability);
      setCatalog(nextCatalog);
      setAvailability(nextAvailability);
      setProvider(resolved.provider);
      setModel(resolved.model);
      setNotice(resolved.notice);
      setLoaded(true);
    });

    return () => {
      cancelled = true;
    };
  }, [saved]);

  useEffect(() => {
    if (loaded) storeSettings({ provider, model });
  }, [provider, model, loaded]);

  const changeProvider = (next: Provider) => {
    if (!availability[next]) {
      setNotice(`${PROVIDER_LABEL[next]} is not available. Check the server configuration.`);
      return;
    }
    setProvider(next);
    setModel(catalog[next][0] ?? "");
    setNotice("");
  };

  const changeModel = (next: string) => {
    setModel(next);
    setNotice("");
  };

  return { provider, model, catalog, availability, notice, loaded, changeProvider, changeModel };
}
