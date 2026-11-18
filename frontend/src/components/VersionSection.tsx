import { useEffect, useRef, useState } from "react";
import { RefreshCw, Download, CheckCircle2, AlertCircle, Power } from "lucide-react";
import {
  UpdateCheck,
  VersionInfo,
  checkForUpdate,
  getUpdateLog,
  getVersion,
  restartApp,
  startUpdate,
} from "../api/client";

type Phase = "idle" | "updating" | "restarting" | "done" | "error";

const POLL_MS = 2500;
const UPDATE_TIMEOUT_MS = 10 * 60 * 1000;
const RESTART_TIMEOUT_MS = 2 * 60 * 1000;
const FAILED_MARKER = "==> FAILED";

export default function VersionSection() {
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = null;
  };

  useEffect(() => {
    getVersion().then(setVersion).catch(() => setVersion(null));
    runCheck();
    return stopPolling;
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

  const finish = () => {
    stopPolling();
    setPhase("done");
    window.setTimeout(() => window.location.reload(), 1200);
  };

  const fail = (message: string) => {
    stopPolling();
    setPhase("error");
    setError(message);
  };

  /** Poll until the server reports a new start time (it restarted), or give up. */
  const waitForRestart = (startedBefore: string | null, timeoutMs: number, withLog: boolean) => {
    const deadline = Date.now() + timeoutMs;
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      if (Date.now() > deadline) {
        fail(
          withLog
            ? "The update didn't finish. See the log above, or run ~/budget-buddy/deploy.sh in Terminal."
            : "Budget Buddy didn't come back after restarting. Check it on the Mac mini.",
        );
        return;
      }
      // The server goes away mid-restart, so failed requests here are expected.
      try {
        if (withLog) {
          const { lines } = await getUpdateLog();
          setLog(lines);
          if (lines.some((l) => l.startsWith(FAILED_MARKER))) {
            fail("The update failed and the app was not restarted. See the log above.");
            return;
          }
        }
        const ver = await getVersion();
        if (ver.started_at && ver.started_at !== startedBefore) finish();
      } catch {
        /* restarting */
      }
    }, POLL_MS);
  };

  const runUpdate = async () => {
    setError(null);
    setLog([]);
    setPhase("updating");
    try {
      await startUpdate();
    } catch (e) {
      fail(e instanceof Error ? e.message : "Could not start update");
      return;
    }
    waitForRestart(version?.started_at ?? null, UPDATE_TIMEOUT_MS, true);
  };

  const runRestart = async () => {
    if (!window.confirm("Restart Budget Buddy? Only the app restarts, not the Mac mini. It takes a few seconds and this page will reload.")) return;
    setError(null);
    setPhase("restarting");
    try {
      await restartApp();
    } catch (e) {
      fail(e instanceof Error ? e.message : "Could not restart");
      return;
    }
    waitForRestart(version?.started_at ?? null, RESTART_TIMEOUT_MS, false);
  };

  const behind = check?.status === "behind" || (check?.status === "diverged" && check.behind > 0);
  const busy = phase === "updating" || phase === "restarting";

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
            <span className="text-gray-400">Running: </span>
            <span className="font-mono font-medium">{version?.running_version || version?.version || "…"}</span>
            {version?.dirty && (
              <span
                className="ml-2 text-xs text-amber-400 cursor-help"
                title={
                  "Files on this machine differ from the installed version:\n" +
                  version.changed_files.join("\n")
                }
              >
                modified locally
              </span>
            )}
            {version?.started_at && (
              <span className="ml-2 text-xs text-gray-500">
                since {new Date(version.started_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={runRestart}
              disabled={busy}
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-1.5 rounded text-sm"
              title="Restarts only the Budget Buddy app (not the Mac mini). Takes a few seconds."
            >
              <Power size={14} /> Restart app
            </button>
            <button
              onClick={runCheck}
              disabled={checking || busy}
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 px-3 py-1.5 rounded text-sm"
            >
              <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
              Check for updates
            </button>
          </div>
        </div>

        {version?.restart_needed && phase === "idle" && (
          <div className="flex items-center justify-between gap-3 flex-wrap rounded-lg border border-amber-700 bg-amber-900/20 px-3 py-2">
            <span className="text-sm text-amber-300">
              Version <span className="font-mono">{version.version}</span> is installed but the app is still running{" "}
              <span className="font-mono">{version.running_version}</span>. Restart to finish the update.
            </span>
            <button
              onClick={runRestart}
              className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded text-sm"
            >
              <Power size={14} /> Restart now
            </button>
          </div>
        )}

        {check?.error && (
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <AlertCircle size={15} /> {check.error}
          </div>
        )}

        {check && !check.error && check.status === "up_to_date" && !version?.restart_needed && (
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

        {busy && (
          <div className="border-t border-gray-700 pt-3 space-y-2">
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <RefreshCw size={15} className="animate-spin" />
              {phase === "updating"
                ? "Updating… Budget Buddy will restart and this page will reload. Don't close this tab."
                : "Restarting Budget Buddy… this page will reload in a few seconds."}
            </div>
          </div>
        )}

        {(phase === "updating" || phase === "error") && log.length > 0 && (
          <pre className="bg-gray-900 rounded p-2 text-[11px] text-gray-400 max-h-40 overflow-auto whitespace-pre-wrap">
            {log.join("\n")}
          </pre>
        )}

        {phase === "done" && (
          <div className="flex items-center gap-2 text-sm text-emerald-400 border-t border-gray-700 pt-3">
            <CheckCircle2 size={15} /> Back up. Reloading…
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
