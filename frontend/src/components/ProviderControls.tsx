import { PROVIDER_LABEL, PROVIDER_ORDER } from "../settings/providers";
import type { ProviderSettingsApi } from "../settings/useProviderSettings";

// The single provider/model chooser. Callers decide where it lives (usually a
// closed settings disclosure), so no workspace shows it by default.
export default function ProviderControls({
  settings,
  label = "AI model",
}: {
  settings: ProviderSettingsApi;
  label?: string;
}) {
  const { provider, model, catalog, availability, notice, changeProvider, changeModel } = settings;
  const options = catalog[provider];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap overflow-hidden rounded border">
        {PROVIDER_ORDER.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => changeProvider(p)}
            aria-pressed={provider === p}
            disabled={!availability[p]}
            title={availability[p] ? PROVIDER_LABEL[p] : `${PROVIDER_LABEL[p]} is not available`}
            className={`px-3 py-1 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40 ${
              provider === p ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            {PROVIDER_LABEL[p]}
          </button>
        ))}
      </div>
      <select
        value={model}
        onChange={(e) => changeModel(e.target.value)}
        aria-label={label}
        disabled={options.length === 0}
        className="border rounded px-2 py-1 text-xs text-gray-700 bg-white disabled:opacity-50"
      >
        {options.length === 0 ? (
          <option value="">No models available</option>
        ) : (
          options.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))
        )}
      </select>
      {notice && <p className="w-full text-xs text-amber-600">{notice}</p>}
    </div>
  );
}
