import { Entity } from "../api/client";

// Single source for entity colors so pills, badges, and charts stay consistent.
export const ENTITY_PALETTE = [
  "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

/** An entity's chosen color, or a stable palette fallback keyed by id. */
export function entityColor(entity: Pick<Entity, "id" | "color">): string {
  return entity.color || ENTITY_PALETTE[entity.id % ENTITY_PALETTE.length];
}
