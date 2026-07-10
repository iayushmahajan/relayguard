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
    amount: 4200,
    currency: "USD",
  },
  null,
  2,
);

export function EventTester({ disabled, onSubmit }: EventTesterProps) {
  const [eventType, setEventType] = useState("invoice.paid");
  const [deduplicationKey, setDeduplicationKey] = useState(
    `demo-${Date.now()}`,
  );
  const [sourceEventId, setSourceEventId] = useState("");
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
      setDeduplicationKey(`demo-${Date.now()}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="grid gap-3" onSubmit={handleSubmit}>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-stone-200">Event type</span>
          <input
            className="rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-stone-100 outline-none focus:border-cyan-300"
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            required
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-stone-200">Deduplication key</span>
          <input
            className="rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-stone-100 outline-none focus:border-cyan-300"
            value={deduplicationKey}
            onChange={(event) => setDeduplicationKey(event.target.value)}
            required
          />
        </label>
      </div>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-stone-200">Source event ID</span>
        <input
          className="rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-stone-100 outline-none focus:border-cyan-300"
          value={sourceEventId}
          onChange={(event) => setSourceEventId(event.target.value)}
          placeholder="optional-provider-event-id"
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-stone-200">Payload JSON</span>
        <textarea
          className="min-h-36 resize-y rounded-md border border-stone-700 bg-stone-950 px-3 py-2 font-mono text-sm text-stone-100 outline-none focus:border-cyan-300"
          value={payloadText}
          onChange={(event) => setPayloadText(event.target.value)}
        />
      </label>
      {error ? <p className="text-sm text-rose-200">{error}</p> : null}
      <button
        className="rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-stone-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-stone-700 disabled:text-stone-400"
        disabled={disabled || submitting}
        type="submit"
      >
        {submitting ? "Submitting..." : "Submit webhook"}
      </button>
    </form>
  );
}
