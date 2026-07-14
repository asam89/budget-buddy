import { useEffect, useRef, useState, KeyboardEvent } from "react";

interface Props {
  value: number | null;
  placeholder?: string;
  // Commit the typed value; resolves on success, rejects to trigger a revert.
  onCommit: (amount: number) => Promise<void>;
  onEnterNext?: () => void;
  onPaste?: (text: string) => void;
  className?: string;
  ariaLabel?: string;
  autoOpen?: boolean;
}

/** An Excel-style cell: type, commit on Enter/blur, Escape cancels, revert on failure. */
export default function EditableAmountCell({
  value,
  placeholder = "—",
  onCommit,
  onEnterNext,
  onPaste,
  className = "",
  ariaLabel,
  autoOpen = false,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState(false);
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const display = value === null || value === undefined ? placeholder : value.toFixed(2);

  const start = () => {
    setDraft(value === null || value === undefined ? "" : String(value));
    setEditing(true);
    setError(false);
  };

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  useEffect(() => {
    if (autoOpen && !editing) start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoOpen]);

  const commit = async () => {
    const parsed = parseFloat(draft.replace(/[$,]/g, ""));
    setEditing(false);
    if (isNaN(parsed) || parsed < 0) {
      // nothing valid typed — leave the DB value untouched
      return;
    }
    if (parsed === value) return;
    setSaving(true);
    try {
      await onCommit(parsed);
      setFlash(true);
      window.setTimeout(() => setFlash(false), 700);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit().then(() => onEnterNext?.());
    } else if (e.key === "Escape") {
      e.preventDefault();
      setEditing(false); // cancel: DB value stays
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        inputMode="decimal"
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={onKeyDown}
        onPaste={
          onPaste
            ? (e) => {
                const text = e.clipboardData.getData("text");
                if (/[\t\n]/.test(text)) {
                  e.preventDefault();
                  setEditing(false);
                  onPaste(text);
                }
              }
            : undefined
        }
        className={`w-full bg-gray-900 border border-emerald-500 rounded px-2 py-1 text-sm text-right outline-none ${className}`}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={start}
      aria-label={ariaLabel}
      className={`w-full text-right px-2 py-1 rounded border text-sm transition-colors ${
        error
          ? "border-red-500 text-red-400"
          : flash
          ? "border-emerald-500 text-emerald-300"
          : "border-transparent hover:border-gray-600 text-gray-100"
      } ${saving ? "opacity-50" : ""} ${className}`}
    >
      {display}
    </button>
  );
}
