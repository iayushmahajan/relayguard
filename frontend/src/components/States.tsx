type StateProps = {
  title: string;
  message: string;
};

export function EmptyState({ title, message }: StateProps) {
  return (
    <div className="rounded-lg border border-dashed border-stone-600 bg-stone-900/35 p-5 text-sm">
      <p className="font-semibold text-stone-100">{title}</p>
      <p className="mt-1 text-stone-400">{message}</p>
    </div>
  );
}

export function ErrorPanel({ title, message }: StateProps) {
  return (
    <div className="rounded-lg border border-rose-400/35 bg-rose-950/35 p-4 text-sm text-rose-100">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-rose-100/75">{message}</p>
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-stone-700 bg-stone-900/45 p-4 text-sm text-stone-300">
      {label}
    </div>
  );
}
