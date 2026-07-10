type MetricCardProps = {
  label: string;
  value: string | number;
  helper: string;
  tone?: "cyan" | "emerald" | "amber" | "rose";
};

const TONES = {
  amber: "border-amber-400/25 bg-amber-500/10 text-amber-100",
  cyan: "border-cyan-400/25 bg-cyan-500/10 text-cyan-100",
  emerald: "border-emerald-400/25 bg-emerald-500/10 text-emerald-100",
  rose: "border-rose-400/25 bg-rose-500/10 text-rose-100",
};

export function MetricCard({
  label,
  value,
  helper,
  tone = "cyan",
}: MetricCardProps) {
  return (
    <article className={`rounded-lg border p-4 ${TONES[tone]}`}>
      <p className="text-xs font-semibold uppercase text-white/65">{label}</p>
      <p className="mt-3 text-3xl font-bold text-white">{value}</p>
      <p className="mt-2 text-sm text-white/70">{helper}</p>
    </article>
  );
}
