type StateProps = {
  title: string;
  message: string;
};

export function EmptyState({ title, message }: StateProps) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5 text-sm">
      <p className="font-semibold text-slate-900">{title}</p>
      <p className="mt-1 text-slate-500">{message}</p>
    </div>
  );
}

export function ErrorPanel({ title, message }: StateProps) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-rose-700">{message}</p>
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
      {label}
    </div>
  );
}
