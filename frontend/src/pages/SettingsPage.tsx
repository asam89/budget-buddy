import { useEffect, useState } from "react";
import { Plus, Check, X, Star, Trash2 } from "lucide-react";
import {
  Entity,
  createEntity,
  deactivateEntity,
  getEntities,
  updateEntity,
} from "../api/client";
import { ENTITY_PALETTE, entityColor } from "../lib/entityColors";
import VersionSection from "../components/VersionSection";

const ENTITY_TYPES = ["personal", "business", "rental", "household", "other"];

export default function SettingsPage() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("business");
  const [newColor, setNewColor] = useState(ENTITY_PALETTE[1]);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setEntities((await getEntities()).filter((e) => e.is_active));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load entities");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    }
  };

  const add = async () => {
    if (!newName.trim()) return;
    await run(async () => {
      await createEntity({ name: newName.trim(), entity_type: newType, color: newColor });
      setNewName("");
      setNewType("business");
      setNewColor(ENTITY_PALETTE[1]);
      setAddOpen(false);
    });
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-2xl font-bold">Settings</h2>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">Entities</h3>
            <p className="text-sm text-gray-400">
              Track separate books — personal plus any businesses. These appear as the
              entity switcher on the dashboard, transactions, and grids.
            </p>
          </div>
          <button
            onClick={() => setAddOpen((o) => !o)}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded-lg text-sm shrink-0"
          >
            <Plus size={16} /> Add entity
          </button>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
            {error}
          </div>
        )}

        {addOpen && (
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[160px]">
              <label className="block text-xs text-gray-400 mb-1">Name</label>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && add()}
                placeholder="e.g. Ignyte"
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Type</label>
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm"
              >
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Color</label>
              <div className="flex gap-1">
                {ENTITY_PALETTE.map((c) => (
                  <button
                    key={c}
                    onClick={() => setNewColor(c)}
                    aria-label={`color ${c}`}
                    className={`w-6 h-6 rounded-full border-2 ${newColor === c ? "border-white" : "border-transparent"}`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>
            <button
              onClick={add}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded text-sm"
            >
              Create
            </button>
          </div>
        )}

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : (
          <div className="bg-gray-800 rounded-xl border border-gray-700 divide-y divide-gray-700/60">
            {entities.map((ent) => (
              <div key={ent.id} className="flex items-center gap-3 px-4 py-3">
                <span
                  className="w-3.5 h-3.5 rounded-full shrink-0"
                  style={{ backgroundColor: entityColor(ent) }}
                />
                {editingId === ent.id ? (
                  <>
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && editName.trim())
                          run(async () => {
                            await updateEntity(ent.id, { name: editName.trim() });
                            setEditingId(null);
                          });
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
                    />
                    <button
                      onClick={() =>
                        editName.trim() &&
                        run(async () => {
                          await updateEntity(ent.id, { name: editName.trim() });
                          setEditingId(null);
                        })
                      }
                      className="p-1 text-gray-400 hover:text-emerald-400"
                      aria-label="Save name"
                    >
                      <Check size={16} />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="p-1 text-gray-400 hover:text-red-400"
                      aria-label="Cancel"
                    >
                      <X size={16} />
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => {
                        setEditingId(ent.id);
                        setEditName(ent.name);
                      }}
                      className="flex-1 text-left font-medium hover:text-emerald-400"
                    >
                      {ent.name}
                    </button>
                    <span className="text-xs text-gray-500">{ent.entity_type}</span>
                    {ent.is_default && (
                      <span className="flex items-center gap-1 text-xs text-amber-400">
                        <Star size={12} /> default
                      </span>
                    )}
                    <div className="flex gap-1 ml-2">
                      {ENTITY_PALETTE.map((c) => (
                        <button
                          key={c}
                          onClick={() => run(() => updateEntity(ent.id, { color: c }))}
                          aria-label={`set ${ent.name} color ${c}`}
                          className={`w-4 h-4 rounded-full border ${entityColor(ent) === c ? "border-white" : "border-transparent"}`}
                          style={{ backgroundColor: c }}
                        />
                      ))}
                    </div>
                    {!ent.is_default && (
                      <>
                        <button
                          onClick={() => run(() => updateEntity(ent.id, { is_default: true }))}
                          className="p-1 text-gray-500 hover:text-amber-400"
                          aria-label={`Make ${ent.name} default`}
                          title="Make default"
                        >
                          <Star size={15} />
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Deactivate "${ent.name}"?`))
                              run(() => deactivateEntity(ent.id));
                          }}
                          className="p-1 text-gray-500 hover:text-red-400"
                          aria-label={`Deactivate ${ent.name}`}
                          title="Deactivate"
                        >
                          <Trash2 size={15} />
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            ))}
            {entities.length === 0 && (
              <p className="px-4 py-6 text-center text-gray-500 text-sm">No entities yet.</p>
            )}
          </div>
        )}
      </section>

      <VersionSection />
    </div>
  );
}
