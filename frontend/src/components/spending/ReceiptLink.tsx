import { Paperclip } from "lucide-react";
import { receiptUrl } from "../../api/client";

/** Small paperclip that opens a transaction's receipt in a new tab. */
export default function ReceiptLink({ id }: { id?: number | null }) {
  if (!id) return null;
  return (
    <a href={receiptUrl(id)} target="_blank" rel="noreferrer" title="Open receipt"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center text-gray-400 hover:text-emerald-400 align-middle">
      <Paperclip size={14} />
      <span className="sr-only">Open receipt</span>
    </a>
  );
}
