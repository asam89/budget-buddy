import { useEffect, useRef, useState } from "react";
import { RefreshCw, Download, CheckCircle2, AlertCircle } from "lucide-react";
import {
  UpdateCheck,
  VersionInfo,
  checkForUpdate,
  getUpdateLog,
  getVersion,
  startUpdate,
} from "../api/client";

type Phase = "idle" | "updating" | "done" | "error";

export default function VersionSection() {
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    getVersion().then(setVersion).catch(() => setVersion(null));
    runCheck();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runCheck = async () => {
    setChecking(true);
    try {
      setCheck(await checkForUpdate());
    } catch (e) {
      setCheck(null);
      setError(e instanceof Error ? e.message : "Update check failed");
    } finally {
      setChecking(false);
    }
  };

  const runUpdate = async () => {
    setError(null);
    setLog([]);
    setPhase("updating");
    try {
      await startUpdate();
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Could not start update");
      return;
    }

    const target = check?.latest_version;
    pollRef.current = window.setInterval(async () => {
      // The server restarts mid-deploy, so these requests can transiently fail;
      // swallow errors and keep polling until it comes back updated.
      try {
        const [logResp, ver] = await Promise.all([getUpdateLog(), getVersion()]);
        setLog(logResp.lines);
        if (target && ver.available && ver.version === target) {
          finishUpdate();
        }
      } catch {
        /* server likely restarting */
      }
    }, 2500);
  };

  const finishUpdate = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = null;
    setPhase("done");
    window.setTimeout(() => window.location.reload(), 1500);
  };

  const behind = check?.status === "behind" || (check?.status === "diverged" && check.behind > 0);

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">App version</h3>
        <p className="text-sm text-gray-400">
          What's running on this machine, and whether it matches the latest on GitHub.
        </p>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm">
            <span className="text-gray-400">Installed: </span>
            <span className="font-mono font-medium">{version?.version ?? "…"}</span>
            {version?.dirty && (
              <span className="ml-2 text-xs text-amber-400">local changes</span>
            )}
            {version?.commit_date && (
              <span className="ml-2 text-xs text-gray-500">
                {new Date(version.commit_date).toLocaleDateString()}
              </span>
            )}
          </div>
          <button
            onClick={runCheck}
            disabled={checking || phase === "updating"}
            className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-1.5 rounded text-sm"
          >
            <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
            Check for updates
          </button>
        </div>

        {check?.error && (
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <AlertCircle size={15} /> {check.error}
          </div>
        )}

        {check && !check.error && check.status === "up_to_date" && (
          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <CheckCircle2 size={15} /> Up to date.
          </div>
        )}

        {check && !check.error && check.status === "ahead" && (
          <div className="text-sm text-gray-400">
            This machine is {check.ahead} commit(s) ahead of GitHub (local work).
          </div>
        )}

        {behind && phase === "idle" && (
          <div className="flex items-center justify-between gap-3 flex-wrap border-t border-gray-700 pt-3">
            <div className="text-sm">
              <span className="text-amber-400 font-medium">Update available</span>
              <span className="text-gray-400">
                {" "}— {check!.behind} commit(s) behind
                {check!.latest_version ? ` · latest ${check!.latest_version}` : ""}
              </span>
            </div>
            <button
              onClick={runUpdate}
              className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded text-sm"
            >
              <Download size={15} /> Update now
            </button>
          </div>
        )}

        {phase === "updating" && (
          <div className="border-t border-gray-700 pt-3 space-y-2">
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <RefreshCw size={15} className="animate-spin" />
              Updating… the app will reload when it's done. Don't close this tab.
            </div>
            {log.length > 0 && (
              <pre className="bg-gray-900 rounded p-2 text-[11px] text-gray-400 max-h-40 overflow-auto whitespace-pre-wrap">
                {log.join("\n")}
              </pre>
            )}
          </div>
        )}

        {phase === "done" && (
          <div className="flex items-center gap-2 text-sm text-emerald-400 border-t border-gray-700 pt-3">
            <CheckCircle2 size={15} /> Updated. Reloading…
          </div>
        )}

        {phase === "error" && error && (
          <div className="flex items-center gap-2 text-sm text-red-400 border-t border-gray-700 pt-3">
            <AlertCircle size={15} /> {error}
          </div>
        )}
      </div>
    </section>
  );
}
