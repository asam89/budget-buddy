import { useEffect, useState } from "react";
import { Cpu, CircleAlert, Loader2 } from "lucide-react";
import { getLlmHealth, LlmHealth } from "../api/client";

/**
 * Shows which local model is assisting, and whether it is reachable.
 * Falls back to an "offline" state when the provider can't be reached.
 */
export default function ModelBadge({ override }: { override?: string | null }) {
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getLlmHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-gray-400 bg-gray-800 border border-gray-700 rounded-full px-3 py-1">
        <Loader2 size={13} className="animate-spin" /> Checking model…
      </span>
    );
  }

  const name = override || health?.provider_name || "none";
  const online = !!health && health.reachable && health.model_available;

  if (online) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-3 py-1">
        <Cpu size={13} /> Assisted by: {name.replace(":", " · ")}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-3 py-1"
      title={health?.error || "The local model could not be reached."}
    >
      <CircleAlert size={13} /> Local model offline{health ? ` (${name})` : ""} — using rules
    </span>
  );
}
