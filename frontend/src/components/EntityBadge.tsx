import { Entity } from "../api/client";
import { entityColor } from "../lib/entityColors";

interface Props {
  entity?: Pick<Entity, "id" | "name" | "color"> | null;
  onClick?: () => void;
  title?: string;
}

/**
 * Colored entity pill used across Transactions/Review. Uses Entity.color (via
 * entityColor) as the single source of truth so a given entity looks the same
 * everywhere. Renders a muted "—" chip when there's no entity.
 */
export default function EntityBadge({ entity, onClick, title }: Props) {
  const clickable = onClick !== undefined;
  const base =
    "inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border";

  if (!entity) {
    return (
      <span
        className={`${base} border-gray-700 text-gray-500 ${clickable ? "cursor-pointer hover:border-gray-500" : ""}`}
        onClick={onClick}
        title={title ?? (clickable ? "Assign entity" : undefined)}
      >
        —
      </span>
    );
  }

  const color = entityColor(entity);
  return (
    <span
      className={`${base} font-medium ${clickable ? "cursor-pointer" : ""}`}
      style={{ color, borderColor: color, backgroundColor: `${color}1a` }}
      onClick={onClick}
      title={title ?? (clickable ? "Change entity" : undefined)}
    >
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      {entity.name}
    </span>
  );
}
