import type { Rating } from "@/lib/api/schemas";
import { Swatch } from "./tile";

export const RATING: Record<Rating, { label: string; swatch: string; text: string }> = {
  under: { label: "Arzon", swatch: "var(--rating-under)", text: "var(--rating-under-text)" },
  fair: { label: "Adolatli", swatch: "var(--rating-fair)", text: "var(--text-2)" },
  over: { label: "Qimmat", swatch: "var(--rating-over)", text: "var(--warning)" },
  no_data: { label: "Ma’lumot yo‘q", swatch: "var(--rating-none)", text: "var(--text-muted)" },
};

export function RatingLabel({ rating }: { rating: Rating }) {
  const r = RATING[rating];
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap" style={{ color: r.text }}>
      <Swatch color={r.swatch} />
      {r.label}
    </span>
  );
}
