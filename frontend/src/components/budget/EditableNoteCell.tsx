import { useEffect, useRef, useState, KeyboardEvent } from "react";

interface Props {
  value: string | null;
  placeholder?: string;
  // Commit the typed note; resolves on success, rejects to trigger a revert.
  onCommit: (note: string) => Promise<void>;
  ariaLabel?: string;
}

/** Click-to-edit free text: commits on Enter/blur, Escape cancels. */
export default function EditableNoteCell({
  value,
  placeholder = "Add note",
  onCommit,
  ariaLabel,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const start = () => {
    setDraft(value ?? "");
    setEditing(true);
    setError(false);
  };

  const commit = async () => {
    const next = draft.trim();
    setEditing(false);
    if (next === (value ?? "")) return;
    setSaving(true);
    try {
      await onCommit(next);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={onKeyDown}
        className="w-full bg-gray-900 border border-emerald-500 rounded px-2 py-1 text-sm outline-none"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={start}
      aria-label={ariaLabel}
      title={value ?? undefined}
      className={`w-full text-left px-2 py-1 rounded border text-sm truncate transition-colors ${
        error
          ? "border-red-500 text-red-400"
          : "border-transparent hover:border-gray-600"
      } ${value ? "text-gray-300" : "text-gray-600"} ${saving ? "opacity-50" : ""}`}
    >
      {value || placeholder}
    </button>
  );
}
