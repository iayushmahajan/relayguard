type MetricCardProps = {
  label: string;
  value: string | number;
  helper: string;
  tone?: "cyan" | "emerald" | "amber" | "rose";
};

const TONES = {
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  cyan: "border-cyan-200 bg-cyan-50 text-cyan-700",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  rose: "border-rose-200 bg-rose-50 text-rose-700",
};

export function MetricCard({
  label,
  value,
  helper,
  tone = "cyan",
}: MetricCardProps) {
  return (
    <article className={`rounded-lg border p-4 shadow-sm ${TONES[tone]}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-3 text-3xl font-bold text-slate-950">{value}</p>
      <p className="mt-2 text-sm text-slate-600">{helper}</p>
    </article>
  );
}
