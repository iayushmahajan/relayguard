type StatusBadgeProps = {
  status: string;
};

const STATUS_STYLES: Record<string, string> = {
  active: "border-emerald-200 bg-emerald-50 text-emerald-700",
  accepted: "border-sky-200 bg-sky-50 text-sky-700",
  approved: "border-sky-200 bg-sky-50 text-sky-700",
  cancelled: "border-slate-200 bg-slate-100 text-slate-600",
  dead_lettered: "border-rose-200 bg-rose-50 text-rose-700",
  delivered: "border-emerald-200 bg-emerald-50 text-emerald-700",
  disabled: "border-slate-200 bg-slate-100 text-slate-600",
  duplicate: "border-amber-200 bg-amber-50 text-amber-700",
  executed: "border-amber-200 bg-amber-50 text-amber-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  fallback: "border-slate-200 bg-slate-100 text-slate-700",
  high: "border-rose-200 bg-rose-50 text-rose-700",
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-700",
  open: "border-rose-200 bg-rose-50 text-rose-700",
  pending: "border-amber-200 bg-amber-50 text-amber-700",
  processing: "border-indigo-200 bg-indigo-50 text-indigo-700",
  rejected: "border-rose-200 bg-rose-50 text-rose-700",
  resolved: "border-emerald-200 bg-emerald-50 text-emerald-700",
  running: "border-indigo-200 bg-indigo-50 text-indigo-700",
  scheduled: "border-cyan-200 bg-cyan-50 text-cyan-700",
  succeeded: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const style =
    STATUS_STYLES[status] ?? "border-slate-200 bg-slate-100 text-slate-600";

  return (
    <span
      className={`inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${style}`}
    >
      <span className="truncate">{status.replaceAll("_", " ")}</span>
    </span>
  );
}
