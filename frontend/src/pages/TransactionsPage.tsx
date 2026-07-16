import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  ColumnDef,
  SortingState,
  RowSelectionState,
} from "@tanstack/react-table";
import {
  getTransactions,
  getTransactionTotals,
  getAccounts,
  getCategories,
  getEntities,
  getSavedViews,
  createSavedView,
  deleteSavedView,
  inlineEditTransaction,
  bulkAssignEntity,
  deleteTransaction,
  exportTransactionsCsv,
  exportTransactionsXlsx,
  exportFullWorkbook,
  Transaction,
  TransactionTotals,
  Account,
  Category,
  Entity,
  SavedView,
} from "../api/client";
import {
  ChevronUp,
  ChevronDown,
  Save,
  Trash2,
  X,
  Search,
  Filter,
  Bookmark,
  Download,
  FileSpreadsheet,
} from "lucide-react";
import EntityBadge from "../components/EntityBadge";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(n);
}

interface Filters {
  account_id?: string;
  entity_id?: string;
  category_id?: string;
  txn_type?: string;
  review_status?: string;
  start_date?: string;
  end_date?: string;
  q?: string;
  min_amount?: string;
  max_amount?: string;
}

function filtersToParams(
  filters: Filters,
  sorting: SortingState,
  limit: number,
  offset: number
): Record<string, string> {
  const params: Record<string, string> = {};
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params[k] = v;
  });
  if (sorting.length > 0) {
    params.sort_by = sorting[0].id;
    params.sort_dir = sorting[0].desc ? "desc" : "asc";
  }
  params.limit = String(limit);
  params.offset = String(offset);
  return params;
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [totals, setTotals] = useState<TransactionTotals | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);

  const [filters, setFilters] = useState<Filters>({});
  const [sorting, setSorting] = useState<SortingState>([
    { id: "date", desc: true },
  ]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [pageSize] = useState(50);
  const [page, setPage] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const [editingCell, setEditingCell] = useState<{
    id: number;
    field: string;
  } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [viewName, setViewName] = useState("");
  const [showSaveView, setShowSaveView] = useState(false);
  const [bulkEntity, setBulkEntity] = useState("");
  const editRef = useRef<HTMLInputElement | HTMLSelectElement>(null);

  // Lookup maps
  const _accountMap = useMemo(
    () => Object.fromEntries(accounts.map((a) => [a.id, a.name])),
    [accounts]
  );
  void _accountMap;
  const categoryMap = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.id, c.name])),
    [categories]
  );
  const entityMap = useMemo(
    () => Object.fromEntries(entities.map((e) => [e.id, e.name])),
    [entities]
  );

  // Load reference data
  useEffect(() => {
    getAccounts().then(setAccounts);
    getCategories().then(setCategories);
    getEntities().then(setEntities);
    getSavedViews().then(setSavedViews);
  }, []);

  // Load transactions
  const fetchData = useCallback(() => {
    const params = filtersToParams(filters, sorting, pageSize, page * pageSize);
    getTransactions(params).then((data) => {
      setTransactions(data);
    });
    // Also fetch totals (without pagination)
    const totalsParams: Record<string, string> = {};
    Object.entries(filters).forEach(([k, v]) => {
      if (v) totalsParams[k] = v;
    });
    getTransactionTotals(totalsParams).then(setTotals);
  }, [filters, sorting, pageSize, page]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Count from data length + detect if more pages
  useEffect(() => {
    if (totals) setTotalCount(totals.count);
  }, [totals]);

  // Inline edit handlers
  const startEdit = (id: number, field: string, currentValue: string) => {
    setEditingCell({ id, field });
    setEditValue(currentValue);
    setTimeout(() => editRef.current?.focus(), 50);
  };

  const commitEdit = async () => {
    if (!editingCell) return;
    const { id, field } = editingCell;

    const payload: Record<string, unknown> = {};
    if (field === "entity_id" || field === "category_id") {
      payload[field] = editValue ? Number(editValue) : undefined;
    } else {
      payload[field] = editValue;
    }

    try {
      await inlineEditTransaction(id, payload);
      fetchData();
    } catch {
      // ignore
    }
    setEditingCell(null);
  };

  const cancelEdit = () => setEditingCell(null);

  // Bulk actions
  const selectedIds = Object.keys(rowSelection)
    .filter((k) => rowSelection[k])
    .map((idx) => transactions[Number(idx)]?.id)
    .filter(Boolean);

  const handleBulkAssign = async () => {
    if (!bulkEntity || selectedIds.length === 0) return;
    await bulkAssignEntity(selectedIds, Number(bulkEntity));
    setRowSelection({});
    setBulkEntity("");
    fetchData();
  };

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    for (const id of selectedIds) {
      await deleteTransaction(id);
    }
    setRowSelection({});
    fetchData();
  };

  // Saved views
  const handleSaveView = async () => {
    if (!viewName.trim()) return;
    await createSavedView({
      name: viewName,
      config: JSON.stringify({ filters, sorting }),
    });
    const views = await getSavedViews();
    setSavedViews(views);
    setViewName("");
    setShowSaveView(false);
  };

  const handleLoadView = (view: SavedView) => {
    try {
      const cfg = JSON.parse(view.config);
      if (cfg.filters) setFilters(cfg.filters);
      if (cfg.sorting) setSorting(cfg.sorting);
      setPage(0);
    } catch {
      // ignore
    }
  };

  const handleDeleteView = async (id: number) => {
    await deleteSavedView(id);
    const views = await getSavedViews();
    setSavedViews(views);
  };

  // Column definitions
  const columns = useMemo<ColumnDef<Transaction>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="accent-emerald-500"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="accent-emerald-500"
          />
        ),
        size: 40,
        enableSorting: false,
      },
      {
        accessorKey: "date",
        header: "Date",
        size: 110,
        cell: ({ row }) => (
          <span className="text-gray-400">{row.original.date}</span>
        ),
      },
      {
        accessorKey: "name",
        header: "Description",
        size: 250,
        cell: ({ row }) => {
          const t = row.original;
          if (
            editingCell?.id === t.id &&
            editingCell.field === "name"
          ) {
            return (
              <input
                ref={editRef as React.RefObject<HTMLInputElement>}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") cancelEdit();
                }}
                className="bg-gray-700 border border-emerald-500 rounded px-1 py-0.5 text-sm w-full"
              />
            );
          }
          return (
            <div
              className="cursor-pointer hover:text-emerald-400"
              onDoubleClick={() => startEdit(t.id, "name", t.name)}
            >
              <p>{t.merchant_name || t.name}</p>
              {t.merchant_name && t.name !== t.merchant_name && (
                <p className="text-xs text-gray-500">{t.name}</p>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "entity_id",
        header: "Entity",
        size: 130,
        cell: ({ row }) => {
          const t = row.original;
          if (
            editingCell?.id === t.id &&
            editingCell.field === "entity_id"
          ) {
            return (
              <select
                ref={editRef as React.RefObject<HTMLSelectElement>}
                value={editValue}
                onChange={(e) => {
                  setEditValue(e.target.value);
                }}
                onBlur={commitEdit}
                className="bg-gray-700 border border-emerald-500 rounded px-1 py-0.5 text-sm"
              >
                <option value="">-- none --</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            );
          }
          const ent = t.entity_id
            ? entities.find((e) => e.id === t.entity_id)
            : null;
          return (
            <EntityBadge
              entity={ent}
              onClick={() =>
                startEdit(t.id, "entity_id", String(t.entity_id || ""))
              }
            />
          );
        },
      },
      {
        accessorKey: "category_id",
        header: "Category",
        size: 130,
        cell: ({ row }) => {
          const t = row.original;
          if (
            editingCell?.id === t.id &&
            editingCell.field === "category_id"
          ) {
            return (
              <select
                ref={editRef as React.RefObject<HTMLSelectElement>}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                className="bg-gray-700 border border-emerald-500 rounded px-1 py-0.5 text-sm"
              >
                <option value="">-- none --</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            );
          }
          return (
            <span
              className="cursor-pointer hover:text-emerald-400 text-xs"
              onDoubleClick={() =>
                startEdit(
                  t.id,
                  "category_id",
                  String(t.category_id || "")
                )
              }
            >
              {t.category_id
                ? categoryMap[t.category_id] || `#${t.category_id}`
                : "—"}
            </span>
          );
        },
      },
      {
        accessorKey: "txn_type",
        header: "Type",
        size: 80,
        cell: ({ row }) => {
          const t = row.original;
          return (
            <span
              className={`text-xs px-2 py-0.5 rounded ${
                t.txn_type === "income"
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "bg-red-500/20 text-red-400"
              }`}
            >
              {t.txn_type || "—"}
            </span>
          );
        },
      },
      {
        accessorKey: "review_status",
        header: "Status",
        size: 90,
        cell: ({ row }) => {
          const t = row.original;
          return (
            <span
              className={`text-xs px-2 py-0.5 rounded ${
                t.review_status === "confirmed"
                  ? "bg-emerald-500/20 text-emerald-400"
                  : t.review_status === "pending"
                  ? "bg-yellow-500/20 text-yellow-400"
                  : "bg-red-500/20 text-red-400"
              }`}
            >
              {t.review_status}
            </span>
          );
        },
      },
      {
        accessorKey: "amount",
        header: "Amount",
        size: 120,
        cell: ({ row }) => {
          const t = row.original;
          return (
            <span
              className={`font-medium ${
                t.amount < 0 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {fmt(t.amount)}
            </span>
          );
        },
      },
      {
        accessorKey: "notes",
        header: "Notes",
        size: 150,
        cell: ({ row }) => {
          const t = row.original;
          if (
            editingCell?.id === t.id &&
            editingCell.field === "notes"
          ) {
            return (
              <input
                ref={editRef as React.RefObject<HTMLInputElement>}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") cancelEdit();
                }}
                className="bg-gray-700 border border-emerald-500 rounded px-1 py-0.5 text-sm w-full"
              />
            );
          }
          return (
            <span
              className="cursor-pointer hover:text-emerald-400 text-xs text-gray-500 truncate block max-w-[150px]"
              onDoubleClick={() =>
                startEdit(t.id, "notes", t.notes || "")
              }
            >
              {t.notes || "—"}
            </span>
          );
        },
      },
    ],
    [editingCell, editValue, entities, categories, entityMap, categoryMap]
  );

  const table = useReactTable({
    data: transactions,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableRowSelection: true,
  });

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Transactions</h2>
        <div className="flex items-center gap-2">
          {/* Saved views dropdown */}
          {savedViews.length > 0 && (
            <div className="relative group">
              <button className="flex items-center gap-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-700">
                <Bookmark size={14} />
                Views
              </button>
              <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-20 min-w-[200px] hidden group-hover:block">
                {savedViews.map((v) => (
                  <div
                    key={v.id}
                    className="flex items-center justify-between px-3 py-2 hover:bg-gray-700 text-sm"
                  >
                    <button
                      onClick={() => handleLoadView(v)}
                      className="flex-1 text-left"
                    >
                      {v.name}
                    </button>
                    <button
                      onClick={() => handleDeleteView(v.id)}
                      className="text-gray-500 hover:text-red-400 ml-2"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={() => setShowSaveView(!showSaveView)}
            className="flex items-center gap-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-700"
          >
            <Save size={14} />
            Save View
          </button>
          <button
            onClick={() => {
              const params: Record<string, string> = {};
              Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
              exportTransactionsCsv(params);
            }}
            className="flex items-center gap-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-700"
            title="Export filtered transactions as CSV"
          >
            <Download size={14} />
            CSV
          </button>
          <button
            onClick={() => {
              const params: Record<string, string> = {};
              Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
              exportTransactionsXlsx(params);
            }}
            className="flex items-center gap-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-700"
            title="Export filtered transactions as XLSX"
          >
            <FileSpreadsheet size={14} />
            XLSX
          </button>
          <button
            onClick={() => exportFullWorkbook()}
            className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 border border-emerald-500 rounded-lg px-3 py-1.5 text-sm"
            title="Export full workbook (all data + pivot sheets)"
          >
            <FileSpreadsheet size={14} />
            Full Export
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1 border rounded-lg px-3 py-1.5 text-sm ${
              showFilters
                ? "bg-emerald-500/20 border-emerald-500 text-emerald-400"
                : "bg-gray-800 border-gray-600 hover:bg-gray-700"
            }`}
          >
            <Filter size={14} />
            Filters
          </button>
        </div>
      </div>

      {/* Save view inline */}
      {showSaveView && (
        <div className="flex items-center gap-2 bg-gray-800 rounded-lg p-3 border border-gray-700">
          <input
            value={viewName}
            onChange={(e) => setViewName(e.target.value)}
            placeholder="View name..."
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm flex-1"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveView();
            }}
          />
          <button
            onClick={handleSaveView}
            className="bg-emerald-600 hover:bg-emerald-500 px-3 py-1 rounded text-sm"
          >
            Save
          </button>
          <button
            onClick={() => setShowSaveView(false)}
            className="text-gray-400 hover:text-gray-200"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Search</label>
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500"
              />
              <input
                value={filters.q || ""}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, q: e.target.value }))
                }
                placeholder="Name or merchant..."
                className="bg-gray-700 border border-gray-600 rounded pl-7 pr-2 py-1.5 text-sm w-full"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Account</label>
            <select
              value={filters.account_id || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, account_id: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="">All accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Entity</label>
            <select
              value={filters.entity_id || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, entity_id: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="">All entities</option>
              {entities.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">
              Category
            </label>
            <select
              value={filters.category_id || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, category_id: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Type</label>
            <select
              value={filters.txn_type || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, txn_type: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="">All types</option>
              <option value="income">Income</option>
              <option value="expense">Expense</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Status</label>
            <select
              value={filters.review_status || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, review_status: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="">All statuses</option>
              <option value="confirmed">Confirmed</option>
              <option value="pending">Pending</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">
              Date from
            </label>
            <input
              type="date"
              value={filters.start_date || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, start_date: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Date to</label>
            <input
              type="date"
              value={filters.end_date || ""}
              onChange={(e) =>
                setFilters((f) => ({ ...f, end_date: e.target.value }))
              }
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm w-full"
            />
          </div>
          <div className="col-span-2 md:col-span-4 flex justify-end">
            <button
              onClick={() => {
                setFilters({});
                setPage(0);
              }}
              className="text-sm text-gray-400 hover:text-gray-200"
            >
              Clear all filters
            </button>
          </div>
        </div>
      )}

      {/* Bulk actions bar */}
      {selectedIds.length > 0 && (
        <div className="bg-gray-800 border border-emerald-500/30 rounded-lg p-3 flex items-center gap-3">
          <span className="text-sm text-emerald-400">
            {selectedIds.length} selected
          </span>
          <select
            value={bulkEntity}
            onChange={(e) => setBulkEntity(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
          >
            <option value="">Assign entity...</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <button
            onClick={handleBulkAssign}
            disabled={!bulkEntity}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-3 py-1 rounded text-sm"
          >
            Apply
          </button>
          <button
            onClick={handleBulkDelete}
            className="bg-red-600 hover:bg-red-500 px-3 py-1 rounded text-sm flex items-center gap-1"
          >
            <Trash2 size={14} />
            Delete
          </button>
          <button
            onClick={() => setRowSelection({})}
            className="text-gray-400 hover:text-gray-200 ml-auto text-sm"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr
                  key={headerGroup.id}
                  className="text-gray-400 border-b border-gray-700 bg-gray-800/50"
                >
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className={`py-3 px-4 ${
                        header.column.id === "amount"
                          ? "text-right"
                          : "text-left"
                      }`}
                      style={{ width: header.getSize() }}
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          className={`flex items-center gap-1 ${
                            header.column.id === "amount"
                              ? "justify-end"
                              : ""
                          } ${
                            header.column.getCanSort()
                              ? "cursor-pointer select-none hover:text-gray-200"
                              : ""
                          }`}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                          {header.column.getIsSorted() === "asc" && (
                            <ChevronUp size={14} />
                          )}
                          {header.column.getIsSorted() === "desc" && (
                            <ChevronDown size={14} />
                          )}
                        </div>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={`border-b border-gray-700/50 hover:bg-gray-700/30 ${
                    row.getIsSelected() ? "bg-emerald-500/10" : ""
                  }`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={`py-3 px-4 ${
                        cell.column.id === "amount" ? "text-right" : ""
                      }`}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {transactions.length === 0 && (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="text-center py-8 text-gray-500"
                  >
                    No transactions found
                  </td>
                </tr>
              )}
            </tbody>
            {/* Footer with totals */}
            {totals && totals.count > 0 && (
              <tfoot>
                <tr className="border-t border-gray-600 bg-gray-800/80 text-gray-300 font-medium">
                  <td className="py-3 px-4" colSpan={2}></td>
                  <td className="py-3 px-4 text-sm">
                    {totals.count} transactions
                  </td>
                  <td className="py-3 px-4 text-xs">
                    {Object.entries(totals.entity_subtotals).map(
                      ([eid, amt]) => (
                        <div key={eid}>
                          {entityMap[Number(eid)] || `#${eid}`}:{" "}
                          {fmt(amt)}
                        </div>
                      )
                    )}
                  </td>
                  <td className="py-3 px-4"></td>
                  <td className="py-3 px-4">
                    <span className="text-xs text-emerald-400">
                      In: {fmt(totals.income)}
                    </span>
                    <br />
                    <span className="text-xs text-red-400">
                      Out: {fmt(totals.expenses)}
                    </span>
                  </td>
                  <td className="py-3 px-4"></td>
                  <td className="py-3 px-4 text-right font-bold">
                    {fmt(totals.sum)}
                  </td>
                  <td className="py-3 px-4"></td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-400">
        <span>
          Page {page + 1} of {totalPages}
          {totalCount > 0 && ` (${totalCount} total)`}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 bg-gray-800 border border-gray-600 rounded disabled:opacity-50 hover:bg-gray-700"
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 bg-gray-800 border border-gray-600 rounded disabled:opacity-50 hover:bg-gray-700"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
