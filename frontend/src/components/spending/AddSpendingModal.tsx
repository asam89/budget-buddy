import { X } from "lucide-react";
import SpendingForm from "./SpendingForm";

export default function AddSpendingModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/60 p-4 overflow-y-auto"
      role="dialog" aria-modal="true" aria-label="Add spending">
      <div className="bg-gray-800 rounded-2xl border border-gray-700 w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">Add spending</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Close"><X size={20} /></button>
        </div>
        <SpendingForm />
      </div>
    </div>
  );
}
