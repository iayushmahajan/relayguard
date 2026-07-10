type StatusBadgeProps = {
  status: string;
};

const STATUS_STYLES: Record<string, string> = {
  active: "border-emerald-300/50 bg-emerald-400/15 text-emerald-100",
  accepted: "border-sky-300/50 bg-sky-400/15 text-sky-100",
  approved: "border-sky-300/50 bg-sky-400/15 text-sky-100",
  cancelled: "border-zinc-400/50 bg-zinc-500/15 text-zinc-100",
  dead_lettered: "border-rose-300/50 bg-rose-400/15 text-rose-100",
  delivered: "border-emerald-300/50 bg-emerald-400/15 text-emerald-100",
  disabled: "border-zinc-400/50 bg-zinc-500/15 text-zinc-100",
  duplicate: "border-amber-300/50 bg-amber-400/15 text-amber-100",
  executed: "border-amber-300/50 bg-amber-400/15 text-amber-100",
  failed: "border-rose-300/50 bg-rose-400/15 text-rose-100",
  open: "border-rose-300/50 bg-rose-400/15 text-rose-100",
  pending: "border-amber-300/50 bg-amber-400/15 text-amber-100",
  processing: "border-violet-300/50 bg-violet-400/15 text-violet-100",
  rejected: "border-rose-300/50 bg-rose-400/15 text-rose-100",
  resolved: "border-emerald-300/50 bg-emerald-400/15 text-emerald-100",
  running: "border-violet-300/50 bg-violet-400/15 text-violet-100",
  scheduled: "border-cyan-300/50 bg-cyan-400/15 text-cyan-100",
  succeeded: "border-emerald-300/50 bg-emerald-400/15 text-emerald-100",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const style =
    STATUS_STYLES[status] ??
    "border-stone-400/50 bg-stone-500/15 text-stone-100";

  return (
    <span
      className={`inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${style}`}
    >
      <span className="truncate">{status.replaceAll("_", " ")}</span>
    </span>
  );
}
