function App() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <div className="mx-auto max-w-3xl rounded-2xl border border-slate-800 bg-slate-900/70 p-10 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
          RelayGuard
        </p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-white">
          RelayGuard Foundation
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-relaxed text-slate-300">
          Phase 0 establishes the frontend shell, backend FastAPI app
          foundation, and development tooling. No application routes or database
          schema are implemented yet.
        </p>
      </div>
    </main>
  );
}

export default App;
