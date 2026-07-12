import { useState } from "react";
import type { FormEvent } from "react";

import type { WebhookDraft } from "../lib/types";

type EventTesterProps = {
  disabled: boolean;
  onSubmit: (draft: WebhookDraft) => Promise<void>;
};

const DEFAULT_PAYLOAD = JSON.stringify(
  {
    invoice_id: "inv_demo_001",
    customer_id: "cus_demo_001",
    amount: 4200,
    currency: "USD",
    paid_at: "2026-07-12T12:00:00Z",
  },
  null,
  2,
);
const DEFAULT_DEDUPLICATION_KEY = "demo-invoice-001";
const DEFAULT_SOURCE_EVENT_ID = "stripe_evt_001";

export function EventTester({ disabled, onSubmit }: EventTesterProps) {
  const [eventType, setEventType] = useState("invoice.paid");
  const [deduplicationKey, setDeduplicationKey] = useState(
    DEFAULT_DEDUPLICATION_KEY,
  );
  const [sourceEventId, setSourceEventId] = useState(DEFAULT_SOURCE_EVENT_ID);
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    let payload: unknown;
    try {
      payload = JSON.parse(payloadText);
    } catch {
      setError("Payload must be valid JSON.");
      return;
    }
    if (
      payload === null ||
      Array.isArray(payload) ||
      typeof payload !== "object"
    ) {
      setError("Payload must be a JSON object.");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({
        event_type: eventType,
        deduplication_key: deduplicationKey,
        source_event_id: sourceEventId,
        payload: payload as Record<string, unknown>,
      });
      const nextId = Date.now();
      setDeduplicationKey(`demo-invoice-${nextId}`);
      setSourceEventId(`stripe_evt_${nextId}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="grid gap-3" onSubmit={handleSubmit}>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-slate-700">Event type</span>
          <input
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            required
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-slate-700">Deduplication key</span>
          <input
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            value={deduplicationKey}
            onChange={(event) => setDeduplicationKey(event.target.value)}
            required
          />
        </label>
      </div>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-slate-700">Source event ID</span>
        <input
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          value={sourceEventId}
          onChange={(event) => setSourceEventId(event.target.value)}
          placeholder="optional-provider-event-id"
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-slate-700">Payload JSON</span>
        <textarea
          className="min-h-56 resize-y rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          value={payloadText}
          onChange={(event) => setPayloadText(event.target.value)}
        />
      </label>
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      <button
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
        disabled={disabled || submitting}
        type="submit"
      >
        {submitting ? "Submitting..." : "Submit webhook"}
      </button>
    </form>
  );
}
