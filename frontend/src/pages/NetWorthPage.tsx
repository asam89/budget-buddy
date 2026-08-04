import { useState, useEffect, FormEvent, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Plus, Trash2, Pencil, Camera, TrendingUp, Home, Building2, Landmark, Wallet, Car, CircleDollarSign } from "lucide-react";
import {
  getNetWorthSummary, getAssets, getLiabilities, getNetWorthSnapshots,
  createAsset, updateAsset, deleteAsset,
  createLiability, updateLiability, deleteLiability,
  recordNetWorthSnapshot, getEntities,
  Asset, Liability, NetWorthSummary, NetWorthSnapshot, Entity,
} from "../api/client";

const ASSET_CLASSES = [
  { key: "cash", label: "Cash", icon: Wallet },
  { key: "investment", label: "Investments", icon: TrendingUp },
  { key: "real_estate", label: "Real Estate", icon: Home },
  { key: "business", label: "Business", icon: Building2 },
  { key: "vehicle", label: "Vehicles", icon: Car },
  { key: "other", label: "Other", icon: CircleDollarSign },
];
const LIABILITY_CLASSES = [
  { key: "mortgage", label: "Mortgages", icon: Home },
  { key: "loan", label: "Loans", icon: Landmark },
  { key: "credit_card", label: "Credit Cards", icon: CircleDollarSign },
  { key: "line_of_credit", label: "Lines of Credit", icon: Landmark },
  { key: "other", label: "Other", icon: CircleDollarSign },
];

const fmt = (n: number) =>
  new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }).format(n);

type EditState =
  | { kind: "asset"; row: Asset | null }
  | { kind: "liability"; row: Liability | null }
  | null;

export default function NetWorthPage() {
  const [summary, setSummary] = useState<NetWorthSummary | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [liabilities, setLiabilities] = useState<Liability[]>([]);
  const [snapshots, setSnapshots] = useState<NetWorthSnapshot[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [edit, setEdit] = useState<EditState>(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(() => {
    Promise.all([
      getNetWorthSummary(), getAssets(), getLiabilities(), getNetWorthSnapshots(),
    ]).then(([s, a, l, snaps]) => {
      setSummary(s);
      setAssets(a);
      setLiabilities(l);
      setSnapshots(snaps);
    });
  }, []);

  useEffect(() => {
    reload();
    getEntities().then(setEntities).catch(() => setEntities([]));
  }, [reload]);

  const handleSnapshot = async () => {
    await recordNetWorthSnapshot();
    reload();
  };

  const handleDeleteAsset = async (id: number) => {
    await deleteAsset(id);
    reload();
  };
  const handleDeleteLiability = async (id: number) => {
    await deleteLiability(id);
    reload();
  };

  const entityName = (id: number | null) =>
    id == null ? null : entities.find((e) => e.id === id)?.name ?? null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Net Worth</h2>
        <div className="flex gap-2">
          <button
            onClick={handleSnapshot}
            className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm"
            title="Save today's totals to the trend chart"
          >
            <Camera size={16} /> Record snapshot
          </button>
          <button
            onClick={() => setEdit({ kind: "asset", row: null })}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm"
          >
            <Plus size={16} /> Add asset
          </button>
          <button
            onClick={() => setEdit({ kind: "liability", row: null })}
            className="flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white px-4 py-2 rounded-lg text-sm"
          >
            <Plus size={16} /> Add liability
          </button>
        </div>
      </div>

      {/* Headline totals */}
      {summary && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
            <p className="text-sm text-gray-400">Total Assets</p>
            <p className="text-2xl font-bold text-emerald-400 mt-1">{fmt(summary.total_assets)}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
            <p className="text-sm text-gray-400">Total Liabilities</p>
            <p className="text-2xl font-bold text-rose-400 mt-1">{fmt(summary.total_liabilities)}</p>
          </div>
          <div className="bg-gray-800 rounded-xl p-5 border-2 border-emerald-500/40">
            <p className="text-sm text-gray-400">Net Worth</p>
            <p className={`text-3xl font-bold mt-1 ${summary.net_worth >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {fmt(summary.net_worth)}
            </p>
          </div>
        </div>
      )}

      {/* Trend chart */}
      <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
        <h3 className="font-semibold mb-4">Net Worth Over Time</h3>
        {snapshots.length >= 2 ? (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={snapshots}>
              <defs>
                <linearGradient id="nwFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="as_of_date" tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} tickFormatter={(v) => fmt(v)} width={90} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                formatter={(v: number) => fmt(v)}
              />
              <Area type="monotone" dataKey="net_worth" stroke="#10b981" fill="url(#nwFill)" name="Net worth" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-500 text-center py-10 text-sm">
            Record at least two snapshots to see your net worth trend. Click “Record snapshot” after
            updating your balances.
          </p>
        )}
      </div>

      {/* Balance sheet: assets & liabilities side by side */}
      <div className="grid lg:grid-cols-2 gap-6">
        <BalanceColumn
          title="Assets"
          accent="emerald"
          classes={ASSET_CLASSES}
          rows={assets.map((a) => ({
            id: a.id, name: a.name, cls: a.asset_class, amount: a.value,
            entity: a.entity_name ?? entityName(a.entity_id), institution: a.institution,
          }))}
          total={summary?.total_assets ?? 0}
          onEdit={(id) => setEdit({ kind: "asset", row: assets.find((a) => a.id === id) ?? null })}
          onDelete={handleDeleteAsset}
        />
        <BalanceColumn
          title="Liabilities"
          accent="rose"
          classes={LIABILITY_CLASSES}
          rows={liabilities.map((l) => ({
            id: l.id, name: l.name, cls: l.liability_class, amount: l.balance,
            entity: l.entity_name ?? entityName(l.entity_id), institution: l.institution,
          }))}
          total={summary?.total_liabilities ?? 0}
          onEdit={(id) => setEdit({ kind: "liability", row: liabilities.find((l) => l.id === id) ?? null })}
          onDelete={handleDeleteLiability}
        />
      </div>

      {/* Per-entity breakdown */}
      {summary && summary.by_entity.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 className="font-semibold mb-4">By Entity</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-700">
                <th className="py-2">Entity</th>
                <th className="py-2 text-right">Assets</th>
                <th className="py-2 text-right">Liabilities</th>
                <th className="py-2 text-right">Net</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_entity.map((b) => (
                <tr key={b.entity_id ?? "unassigned"} className="border-b border-gray-700/50">
                  <td className="py-2">{b.entity_name}</td>
                  <td className="py-2 text-right text-emerald-400">{fmt(b.assets)}</td>
                  <td className="py-2 text-right text-rose-400">{fmt(b.liabilities)}</td>
                  <td className={`py-2 text-right font-semibold ${b.net >= 0 ? "text-gray-100" : "text-rose-400"}`}>
                    {fmt(b.net)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {edit && (
        <EntryForm
          state={edit}
          entities={entities}
          saving={saving}
          onClose={() => setEdit(null)}
          onSubmit={async (payload) => {
            setSaving(true);
            try {
              if (edit.kind === "asset") {
                if (edit.row) await updateAsset(edit.row.id, payload);
                else await createAsset(payload as never);
              } else {
                const lp = { ...payload, balance: payload.value, liability_class: payload.asset_class } as never;
                if (edit.row) await updateLiability(edit.row.id, lp);
                else await createLiability(lp);
              }
              setEdit(null);
              reload();
            } finally {
              setSaving(false);
            }
          }}
        />
      )}
    </div>
  );
}

interface Row {
  id: number;
  name: string;
  cls: string;
  amount: number;
  entity: string | null;
  institution: string | null;
}

function BalanceColumn({
  title, accent, classes, rows, total, onEdit, onDelete,
}: {
  title: string;
  accent: "emerald" | "rose";
  classes: { key: string; label: string; icon: typeof Home }[];
  rows: Row[];
  total: number;
  onEdit: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const amountColor = accent === "emerald" ? "text-emerald-400" : "text-rose-400";
  return (
    <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">{title}</h3>
        <span className={`font-bold ${amountColor}`}>{fmt(total)}</span>
      </div>
      {rows.length === 0 && (
        <p className="text-gray-500 text-sm py-4">Nothing added yet.</p>
      )}
      <div className="space-y-4">
        {classes.map((c) => {
          const inClass = rows.filter((r) => r.cls === c.key);
          if (inClass.length === 0) return null;
          const Icon = c.icon;
          const subtotal = inClass.reduce((s, r) => s + r.amount, 0);
          return (
            <div key={c.key}>
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-400 mb-1">
                <Icon size={14} /> {c.label}
                <span className="ml-auto normal-case text-gray-500">{fmt(subtotal)}</span>
              </div>
              <div className="space-y-1">
                {inClass.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 group px-2 py-1.5 rounded-lg hover:bg-gray-700/40">
                    <div className="min-w-0">
                      <p className="truncate">{r.name}</p>
                      {(r.entity || r.institution) && (
                        <p className="text-xs text-gray-500 truncate">
                          {[r.institution, r.entity].filter(Boolean).join(" · ")}
                        </p>
                      )}
                    </div>
                    <span className={`ml-auto ${amountColor}`}>{fmt(r.amount)}</span>
                    <button
                      onClick={() => onEdit(r.id)}
                      className="text-gray-500 hover:text-gray-200 opacity-0 group-hover:opacity-100"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => onDelete(r.id)}
                      className="text-gray-500 hover:text-rose-400 opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface FormPayload {
  name: string;
  asset_class: string;
  value: number;
  entity_id: number | null;
  institution: string | null;
  notes: string | null;
}

function EntryForm({
  state, entities, saving, onClose, onSubmit,
}: {
  state: NonNullable<EditState>;
  entities: Entity[];
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: FormPayload) => void;
}) {
  const isAsset = state.kind === "asset";
  const classes = isAsset ? ASSET_CLASSES : LIABILITY_CLASSES;
  const existing = state.row;

  const initialClass = existing
    ? (isAsset ? (existing as Asset).asset_class : (existing as Liability).liability_class)
    : classes[0].key;
  const initialAmount = existing
    ? (isAsset ? (existing as Asset).value : (existing as Liability).balance)
    : 0;

  const [name, setName] = useState(existing?.name ?? "");
  const [cls, setCls] = useState(initialClass);
  const [amount, setAmount] = useState(String(initialAmount));
  const [entityId, setEntityId] = useState<string>(existing?.entity_id ? String(existing.entity_id) : "");
  const [institution, setInstitution] = useState(existing?.institution ?? "");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      asset_class: cls,
      value: parseFloat(amount) || 0,
      entity_id: entityId ? parseInt(entityId, 10) : null,
      institution: institution || null,
      notes: null,
    });
  };

  const verb = existing ? "Edit" : "Add";
  const noun = isAsset ? "asset" : "liability";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="bg-gray-800 rounded-xl p-6 border border-gray-700 w-full max-w-md space-y-4"
      >
        <h3 className="text-lg font-semibold">{verb} {noun}</h3>
        <div className="space-y-3">
          <label className="block text-sm">
            <span className="text-gray-400">Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder={isAsset ? "e.g. Family home" : "e.g. Home mortgage"}
              className="mt-1 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-gray-400">{isAsset ? "Type" : "Type"}</span>
              <select
                value={cls}
                onChange={(e) => setCls(e.target.value)}
                className="mt-1 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              >
                {classes.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-gray-400">{isAsset ? "Value" : "Balance owed"}</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="mt-1 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-gray-400">Entity (optional)</span>
              <select
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
                className="mt-1 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              >
                <option value="">Unassigned</option>
                {entities.map((en) => (
                  <option key={en.id} value={en.id}>{en.name}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-gray-400">Institution (optional)</span>
              <input
                value={institution}
                onChange={(e) => setInstitution(e.target.value)}
                placeholder="e.g. RBC"
                className="mt-1 w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              />
            </label>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-gray-200">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
