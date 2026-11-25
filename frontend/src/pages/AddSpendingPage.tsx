import { Link } from "react-router-dom";
import SpendingForm from "../components/spending/SpendingForm";

/** Full-screen, phone-friendly quick add. Save /add to your home screen. */
export default function AddSpendingPage() {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 px-4 py-5 max-w-md mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="w-8 h-8" />
          <h1 className="text-xl font-bold">Add spending</h1>
        </div>
        <Link to="/" className="text-sm text-gray-400 hover:text-white">Open app →</Link>
      </div>
      <SpendingForm />
      <p className="mt-6 text-xs text-gray-500">
        Tip: on iPhone, tap Share → Add to Home Screen to open this page in one tap.
      </p>
    </div>
  );
}
