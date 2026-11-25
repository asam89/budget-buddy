import { FormEvent, useEffect, useRef, useState } from "react";
import { Camera, CheckCircle2, Loader2, Paperclip, X } from "lucide-react";
import {
  ReceiptDraft, SpendingOptions, SpendingSaved, addSpending, getSpendingOptions, receiptUrl, scanReceipt,
} from "../../api/client";

const NEW_CATEGORY = "__new__";
const LAST_CATEGORY_KEY = "spending.lastCategory";
const LAST_ENTITY_KEY = "spending.lastEntity";

function readNum(key: string): number | null {
  try {
    const v = localStorage.getItem(key);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}
function writeNum(key: string, v: number | null) {
  try {
    if (v === null) localStorage.removeItem(key);
    else localStorage.setItem(key, String(v));
  } catch {
    /* storage unavailable: fine */
  }
}

const fmt = (n: number) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);

interface Props {
  /** Called after a save, e.g. to close a modal or refresh a grid. */
  onSaved?: (saved: SpendingSaved) => void;
  autoFocus?: boolean;
}

/**
 * Quick add + receipt scan. A receipt fills the form in; nothing is recorded
 * until Save. Remembers the last category and business for the next entry.
 */
export default function SpendingForm({ onSaved, autoFocus = true }: Props) {
  const [opts, setOpts] = useState<SpendingOptions | null>(null);
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [merchant, setMerchant] = useState("");
  const [date, setDate] = useState("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [newCategory, setNewCategory] = useState("");
  const [entityId, setEntityId] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [receipt, setReceipt] = useState<ReceiptDraft | null>(null);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SpendingSaved | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const amountRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSpendingOptions()
      .then((o) => {
        setOpts(o);
        setDate(o.today);
        const lastCat = readNum(LAST_CATEGORY_KEY);
        if (lastCat && o.categories.some((c) => c.id === lastCat)) setCategoryId(String(lastCat));
        const lastEnt = readNum(LAST_ENTITY_KEY);
        const ent = lastEnt && o.entities.some((e) => e.id === lastEnt) ? lastEnt : o.default_entity_id;
        if (ent) setEntityId(String(ent));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load categories"));
  }, []);

  useEffect(() => {
    if (autoFocus && opts) amountRef.current?.focus();
  }, [autoFocus, opts]);

  const reset = () => {
    setAmount("");
    setDescription("");
    setMerchant("");
    setNotes("");
    setReceipt(null);
    setNewCategory("");
    if (opts) setDate(opts.today);
    amountRef.current?.focus();
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setSaved(null);
    setScanning(true);
    try {
      const d = await scanReceipt(file);
      setReceipt(d);
      if (d.total !== null) setAmount(d.total.toFixed(2));
      if (d.merchant) {
        setMerchant(d.merchant);
        if (!description) setDescription(d.summary ? `${d.merchant}: ${d.summary}` : d.merchant);
      }
      if (d.date) setDate(d.date);
      if (d.category_id) setCategoryId(String(d.category_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't read that file");
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(null);
    const value = parseFloat(amount.replace(/[$,]/g, ""));
    if (!(value > 0)) {
      setError("Enter the amount");
      return;
    }
    setSaving(true);
    try {
      const isNew = categoryId === NEW_CATEGORY;
      const result = await addSpending({
        amount: value,
        description: description.trim() || merchant.trim(),
        merchant: merchant.trim() || undefined,
        date: date || undefined,
        category_id: categoryId && !isNew ? Number(categoryId) : null,
        new_category: isNew ? newCategory.trim() : undefined,
        entity_id: entityId ? Number(entityId) : null,
        notes: notes.trim() || undefined,
        receipt_id: receipt?.receipt_id ?? null,
      });
      writeNum(LAST_CATEGORY_KEY, result.category_id);
      writeNum(LAST_ENTITY_KEY, entityId ? Number(entityId) : null);
      if (isNew) {
        const o = await getSpendingOptions();
        setOpts(o);
        if (result.category_id) setCategoryId(String(result.category_id));
      }
      setSaved(result);
      onSaved?.(result);
      reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  const field =
    "w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-base text-gray-100 placeholder-gray-500 focus:outline-none focus:border-emerald-500";
  const catName = (id: number | null) => opts?.categories.find((c) => c.id === id)?.name;

  return (
    <form onSubmit={submit} className="space-y-3">
      {/* Receipt */}
      <input
        ref={fileRef}
        type="file"
        accept="image/*,application/pdf"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0])}
      />
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onFile(e.dataTransfer.files?.[0]);
        }}
        className="rounded-xl border border-dashed border-gray-600 p-3 flex items-center gap-3"
      >
        {receipt ? (
          <>
            <a href={receiptUrl(receipt.receipt_id)} target="_blank" rel="noreferrer"
              className="flex items-center gap-2 text-sm text-emerald-400 hover:underline min-w-0">
              <Paperclip size={16} className="shrink-0" /> <span className="truncate">Receipt attached</span>
            </a>
            <button type="button" onClick={() => setReceipt(null)} className="ml-auto text-gray-400 hover:text-white"
              aria-label="Remove receipt"><X size={16} /></button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => fileRef.current?.click()} disabled={scanning}
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg px-3 py-2 text-sm shrink-0">
              {scanning ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}
              {scanning ? "Reading receipt…" : "Snap or upload receipt"}
            </button>
            <span className="text-xs text-gray-400 hidden sm:inline">or drop a photo/PDF here. Optional.</span>
          </>
        )}
      </div>
      {receipt && receipt.warnings.length > 0 && (
        <ul className="text-xs text-amber-300 space-y-0.5">
          {receipt.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}

      {/* Details */}
      <div className="grid grid-cols-2 gap-3">
        <label className="col-span-1 text-xs text-gray-400 space-y-1">
          <span>Amount</span>
          <input ref={amountRef} inputMode="decimal" placeholder="0.00" value={amount}
            onChange={(e) => setAmount(e.target.value)} className={`${field} text-lg font-semibold`} required />
        </label>
        <label className="col-span-1 text-xs text-gray-400 space-y-1">
          <span>Date</span>
          <input type="date" value={date} max={opts?.today} onChange={(e) => setDate(e.target.value)} className={field} />
        </label>
      </div>
      <label className="block text-xs text-gray-400 space-y-1">
        <span>What was it?</span>
        <input placeholder="e.g. Movie night, Coffee with Sam" value={description}
          onChange={(e) => setDescription(e.target.value)} className={field} required={!merchant} />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs text-gray-400 space-y-1">
          <span>Category</span>
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={field}>
            <option value="">Choose…</option>
            {opts?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            <option value={NEW_CATEGORY}>+ New category…</option>
          </select>
        </label>
        <label className="text-xs text-gray-400 space-y-1">
          <span>Business</span>
          <select value={entityId} onChange={(e) => setEntityId(e.target.value)} className={field}>
            {opts?.entities.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </label>
      </div>
      {categoryId === NEW_CATEGORY && (
        <input placeholder="New category name, e.g. Leisure & Misc" value={newCategory}
          onChange={(e) => setNewCategory(e.target.value)} className={field} required />
      )}
      <details className="text-xs text-gray-400">
        <summary className="cursor-pointer select-none">More (store, note)</summary>
        <div className="space-y-3 pt-2">
          <input placeholder="Store / merchant" value={merchant} onChange={(e) => setMerchant(e.target.value)} className={field} />
          <input placeholder="Note" value={notes} onChange={(e) => setNotes(e.target.value)} className={field} />
        </div>
      </details>

      {error && <p className="text-sm text-red-400">{error}</p>}
      <button type="submit" disabled={saving || scanning}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-3 rounded-lg text-base">
        {saving ? "Saving…" : "Save spending"}
      </button>

      {saved && (
        <div role="status" className="rounded-lg border border-emerald-700 bg-emerald-900/30 p-3 text-sm space-y-1">
          <p className="flex items-center gap-2 text-emerald-300">
            <CheckCircle2 size={16} />
            {saved.created ? "Saved" : "Already saved"}: {fmt(saved.amount)} · {saved.name}
            {catName(saved.category_id) ? ` · ${catName(saved.category_id)}` : ""}
          </p>
          {saved.manual_actual_overrides && (
            <p className="text-amber-300 text-xs">
              This category's actual for the month was typed in on the Expenses page, which overrides spending
              entries. Clear that cell to let entries add up automatically.
            </p>
          )}
        </div>
      )}
    </form>
  );
}
