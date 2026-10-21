import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, FlaskConical, RefreshCw } from "lucide-react";
import {
  LlmHealth,
  LlmProviderName,
  LlmSettings,
  LlmTestResult,
  getLlmHealth,
  getLlmModels,
  getLlmSettings,
  testLlm,
  updateLlmSettings,
} from "../api/client";

const errMsg = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

export default function AiProviderSection() {
  const [saved, setSaved] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<LlmProviderName>("ollama");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<LlmTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applySettings = (s: LlmSettings) => {
    setSaved(s);
    setProvider(s.provider);
    setBaseUrl(s.ollama_base_url);
    setModel(s.ollama_model);
  };

  const loadModels = async () => {
    try {
      setModels((await getLlmModels()).models);
    } catch {
      setModels([]);
    }
  };

  const runHealth = async () => {
    setChecking(true);
    try {
      setHealth(await getLlmHealth());
    } catch (e) {
      setHealth(null);
      setError(errMsg(e, "Health check failed"));
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        applySettings(await getLlmSettings());
      } catch (e) {
        setError(errMsg(e, "Failed to load AI settings"));
        return;
      }
      await Promise.all([loadModels(), runHealth()]);
    })();
  }, []);

  const dirty =
    !!saved &&
    (provider !== saved.provider ||
      baseUrl.trim() !== saved.ollama_base_url ||
      model.trim() !== saved.ollama_model);

  const save = async () => {
    if (!saved) return;
    setError(null);
    setTest(null);
    setSaving(true);
    try {
      applySettings(
        await updateLlmSettings({
          provider,
          ollama_base_url: baseUrl.trim(),
          ollama_model: model.trim(),
        }),
      );
      await Promise.all([loadModels(), runHealth()]);
    } catch (e) {
      setError(errMsg(e, "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    setError(null);
    setTest(null);
    setTesting(true);
    try {
      setTest(await testLlm());
    } catch (e) {
      setError(errMsg(e, "Test failed"));
    } finally {
      setTesting(false);
    }
  };

  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;
  const healthy = !!health && health.reachable && health.model_available;

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">AI provider</h3>
        <p className="text-sm text-gray-400">
          Which model reads statements, sets up budgets and writes expense insights. On-device
          Ollama keeps your data on this machine; Claude sends it to Anthropic.
        </p>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {!saved ? (
        !error && <p className="text-gray-500">Loading…</p>
      ) : (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-4">
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="llm-provider"
                checked={provider === "ollama"}
                onChange={() => setProvider("ollama")}
              />
              On-device (Ollama)
            </label>
            <label
              className={`flex items-center gap-2 text-sm ${saved.anthropic_configured ? "cursor-pointer" : "opacity-50"}`}
              title={saved.anthropic_configured ? "" : "Set ANTHROPIC_API_KEY in .env to enable"}
            >
              <input
                type="radio"
                name="llm-provider"
                checked={provider === "anthropic"}
                disabled={!saved.anthropic_configured}
                onChange={() => setProvider("anthropic")}
              />
              Claude (cloud)
              {!saved.anthropic_configured && (
                <span className="text-xs text-gray-500">needs ANTHROPIC_API_KEY</span>
              )}
            </label>
          </div>

          {provider === "ollama" && (
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[200px]">
                <label htmlFor="ollama-url" className="block text-xs text-gray-400 mb-1">
                  Ollama URL
                </label>
                <input
                  id="ollama-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm font-mono"
                />
              </div>
              <div className="min-w-[180px]">
                <label htmlFor="ollama-model" className="block text-xs text-gray-400 mb-1">
                  Model
                </label>
                <div className="flex gap-1">
                  <select
                    id="ollama-model"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm font-mono"
                  >
                    {modelOptions.length === 0 && <option value="">No models found</option>}
                    {modelOptions.map((m) => (
                      <option key={m} value={m}>
                        {m}
                        {models.includes(m) ? "" : " (not installed)"}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={loadModels}
                    className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded"
                    aria-label="Refresh model list"
                    title="Refresh model list"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span className="text-xs text-gray-500">
              Requests time out after {saved.llm_timeout_seconds}s.
            </span>
            <button
              onClick={save}
              disabled={!dirty || saving}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white px-3 py-1.5 rounded text-sm"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>

          <div className="border-t border-gray-700 pt-3 space-y-2">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="text-sm min-w-0">
                {checking ? (
                  <span className="text-gray-400">Checking…</span>
                ) : health ? (
                  <span
                    className={`flex items-center gap-2 ${healthy ? "text-emerald-400" : "text-amber-400"}`}
                  >
                    {healthy ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                    <span className="font-mono">{health.provider_name}</span>
                    {healthy
                      ? ` ready · ${Math.round(health.latency_ms)} ms`
                      : health.reachable
                        ? " reachable, model missing"
                        : " not reachable"}
                  </span>
                ) : null}
                {health?.error && !healthy && (
                  <p className="text-xs text-gray-400 mt-1 break-words">{health.error}</p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={runHealth}
                  disabled={checking}
                  className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-1.5 rounded text-sm"
                >
                  <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
                  Check
                </button>
                <button
                  onClick={runTest}
                  disabled={testing || dirty}
                  title={dirty ? "Save first" : "Parse a sample statement with the saved provider"}
                  className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-1.5 rounded text-sm"
                >
                  <FlaskConical size={14} className={testing ? "animate-pulse" : ""} />
                  {testing ? "Testing…" : "Run test"}
                </button>
              </div>
            </div>
            {test && (
              <div
                className={`flex items-start gap-2 text-sm ${test.success ? "text-emerald-400" : "text-red-400"}`}
              >
                {test.success ? <CheckCircle2 size={15} className="mt-0.5" /> : <AlertCircle size={15} className="mt-0.5" />}
                <span className="break-words">
                  {test.success
                    ? `Test passed: ${test.parsed_count ?? 0} of 4 sample transactions read in ${(test.latency_ms / 1000).toFixed(1)}s`
                    : `Test failed after ${(test.latency_ms / 1000).toFixed(1)}s: ${test.error}`}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
