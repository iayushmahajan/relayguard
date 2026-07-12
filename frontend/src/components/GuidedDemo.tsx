import { useMemo, useState } from "react";

import { api } from "../lib/api";
import type {
  DeadLetter,
  Delivery,
  Destination,
  Integration,
  ReplayRequest,
  RoutingRule,
  WebhookResult,
} from "../lib/types";
import { EmptyState } from "./States";
import { StatusBadge } from "./StatusBadge";

type ScenarioId = "success" | "retry" | "recovery";
type StepStatus = "not_started" | "running" | "completed" | "failed";

type ScenarioStep = {
  label: string;
  status: StepStatus;
  detail?: string;
};

type ScenarioConfig = {
  id: ScenarioId;
  title: string;
  purpose: string;
  destinationName: string;
  destinationUrl: string;
  ruleName: string;
  eventType: string;
  steps: string[];
};

type ScenarioResult = {
  title: string;
  eventId?: string;
  deliveryId?: string;
  deadLetterId?: string;
  replayRequestId?: string;
  summary: string;
};

type GuidedDemoProps = {
  destinations: Destination[];
  onNavigate: (
    page: "events" | "deliveries" | "recovery" | "route-setup",
  ) => void;
  onRefreshDashboard: () => Promise<void>;
  onRefreshIntegration: () => Promise<void>;
  onSelectDeadLetter: (deadLetterId: string) => void;
  onSelectDelivery: (deliveryId: string) => void;
  onSelectEvent: (eventId: string) => void;
  selectedIntegration: Integration | undefined;
};

const SUCCESS_URL = "http://127.0.0.1:9000/success";
const FAILURE_URL = "http://127.0.0.1:9000/fail";
const REJECT_URL = "http://127.0.0.1:9000/reject";

const SCENARIOS: ScenarioConfig[] = [
  {
    id: "success",
    title: "Successful Delivery",
    purpose: "Show the happy path from webhook intake to delivered attempt.",
    destinationName: "Success Receiver",
    destinationUrl: SUCCESS_URL,
    ruleName: "Demo Success Route",
    eventType: "demo.success",
    steps: [
      "Activate integration",
      "Create or reuse destination",
      "Create or reuse routing rule",
      "Submit webhook",
      "Schedule delivery",
      "Execute delivery",
      "Inspect delivered result",
    ],
  },
  {
    id: "retry",
    title: "Temporary Failure + Retry",
    purpose: "Show how RelayGuard records retryable downstream failures.",
    destinationName: "Retry Receiver",
    destinationUrl: FAILURE_URL,
    ruleName: "Demo Retry Route",
    eventType: "demo.retry",
    steps: [
      "Activate integration",
      "Create or reuse retry destination",
      "Create or reuse routing rule",
      "Submit webhook",
      "Schedule delivery",
      "Execute delivery",
      "Inspect retry job",
    ],
  },
  {
    id: "recovery",
    title: "Permanent Failure + Recovery",
    purpose: "Show dead-letter recovery with an approved replay.",
    destinationName: "Reject Receiver",
    destinationUrl: REJECT_URL,
    ruleName: "Demo Recovery Route",
    eventType: "demo.recovery",
    steps: [
      "Activate integration",
      "Create or reuse reject destination",
      "Create or reuse routing rule",
      "Submit webhook",
      "Schedule delivery",
      "Execute rejected delivery",
      "Create and approve replay",
      "Repair destination and replay",
    ],
  },
];

export function GuidedDemo({
  destinations,
  onNavigate,
  onRefreshDashboard,
  onRefreshIntegration,
  onSelectDeadLetter,
  onSelectDelivery,
  onSelectEvent,
  selectedIntegration,
}: GuidedDemoProps) {
  const [activeScenario, setActiveScenario] = useState<ScenarioId | null>(null);
  const [steps, setSteps] = useState<ScenarioStep[]>([]);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const destinationNames = useMemo(
    () =>
      new Map(
        destinations.map((destination) => [
          destination.destination_id,
          destination.name,
        ]),
      ),
    [destinations],
  );

  async function runScenario(scenario: ScenarioConfig) {
    setActiveScenario(scenario.id);
    setResult(null);
    setError(null);
    setSteps(
      scenario.steps.map((label) => ({
        label,
        status: "not_started",
      })),
    );

    try {
      if (!selectedIntegration) {
        throw new Error(
          "Seed and select a demo integration before running a scenario.",
        );
      }
      const slug = selectedIntegration.slug;
      let destination: Destination | undefined;
      let routingRule: RoutingRule | undefined;
      let webhook: WebhookResult | undefined;
      let delivery: Delivery | undefined;
      let deadLetter: DeadLetter | undefined;
      let replayRequest: ReplayRequest | undefined;

      await runStep(0, async () => {
        if (selectedIntegration.status !== "active") {
          await api.updateIntegration(slug, "active");
          await onRefreshDashboard();
        }
        return "Integration is active.";
      });

      await runStep(1, async () => {
        destination = await ensureDestination(slug, scenario);
        await onRefreshIntegration();
        return `${destination.name} routes to ${destination.endpoint_url}.`;
      });

      await runStep(2, async () => {
        if (!destination) {
          throw new Error("Destination setup did not complete.");
        }
        routingRule = await ensureRoutingRule(slug, scenario, destination);
        await onRefreshIntegration();
        return `${routingRule.event_type} routes to ${destination.name}.`;
      });

      await runStep(3, async () => {
        webhook = await api.submitWebhook(slug, demoWebhook(scenario));
        onSelectEvent(webhook.event_id);
        return `Event ${shortId(webhook.event_id)} was accepted.`;
      });

      await runStep(4, async () => {
        if (!webhook) {
          throw new Error("Webhook submission did not complete.");
        }
        const scheduled = await api.scheduleDeliveries(webhook.event_id);
        return `Scheduled ${scheduled.scheduled_count}; already scheduled ${scheduled.already_scheduled_count}.`;
      });

      await runStep(5, async () => {
        if (!webhook || !destination || !routingRule) {
          throw new Error("Delivery setup did not complete.");
        }
        const deliveries = await api.listDeliveries(webhook.event_id);
        delivery =
          deliveries.find(
            (candidate) =>
              candidate.destination_id === destination?.destination_id &&
              candidate.routing_rule_id === routingRule?.routing_rule_id,
          ) ?? deliveries[0];
        if (!delivery) {
          throw new Error("No delivery was scheduled for the event.");
        }
        onSelectDelivery(delivery.delivery_id);
        const execution = await api.executeDelivery(delivery.delivery_id);
        delivery = { ...delivery, status: execution.status };
        if (scenario.id === "success" && execution.status !== "delivered") {
          throw new Error(
            "Expected a delivered result. Is the demo receiver running on port 9000?",
          );
        }
        if (scenario.id === "retry" && !execution.retry_scheduled) {
          throw new Error("Expected a retry job after the retry scenario.");
        }
        if (scenario.id === "recovery" && !execution.dead_lettered) {
          throw new Error(
            "Expected a dead letter after the recovery rejection.",
          );
        }
        return `Delivery ${shortId(delivery.delivery_id)} is ${execution.status}.`;
      });

      if (scenario.id === "success") {
        await runStep(6, async () => {
          if (!delivery) {
            throw new Error("Delivery execution did not complete.");
          }
          const attempts = await api.listDeliveryAttempts(delivery.delivery_id);
          await onRefreshDashboard();
          return `${attempts.length} attempt recorded; delivery is complete.`;
        });
        setResult({
          title: scenario.title,
          eventId: webhook?.event_id,
          deliveryId: delivery?.delivery_id,
          summary:
            "Webhook received -> event created -> route matched -> delivery scheduled -> attempt succeeded -> delivered.",
        });
        return;
      }

      if (scenario.id === "retry") {
        await runStep(6, async () => {
          if (!delivery) {
            throw new Error("Delivery execution did not complete.");
          }
          const retryJobs = await api.listRetryJobs(delivery.delivery_id);
          if (retryJobs.length === 0) {
            throw new Error("No retry job was created.");
          }
          await onRefreshDashboard();
          return `${retryJobs.length} retry job is pending.`;
        });
        setResult({
          title: scenario.title,
          eventId: webhook?.event_id,
          deliveryId: delivery?.delivery_id,
          summary:
            "Webhook received -> event created -> delivery failed with 503 -> retry job created.",
        });
        return;
      }

      await runStep(6, async () => {
        if (!delivery) {
          throw new Error("Delivery execution did not complete.");
        }
        const deadLetters = await api.listDeadLetters();
        deadLetter = deadLetters.find(
          (candidate) => candidate.delivery_id === delivery?.delivery_id,
        );
        if (!deadLetter) {
          throw new Error("No dead letter was created.");
        }
        onSelectDeadLetter(deadLetter.dead_letter_id);
        replayRequest = await api.createReplayRequest(
          deadLetter.dead_letter_id,
          "Downstream was repaired during the guided demo.",
          "guided-demo",
        );
        replayRequest = await api.approveReplayRequest(
          replayRequest.replay_request_id,
          "guided-demo",
          "Approved as part of the guided recovery scenario.",
        );
        return `Replay ${shortId(replayRequest.replay_request_id)} approved.`;
      });

      await runStep(7, async () => {
        if (!destination || !replayRequest) {
          throw new Error("Replay setup did not complete.");
        }
        await api.updateDestination(slug, destination.destination_id, {
          endpoint_url: SUCCESS_URL,
          status: "active",
        });
        const replay = await api.executeReplayRequest(
          replayRequest.replay_request_id,
        );
        if (!replay.dead_letter_resolved) {
          throw new Error("Replay ran but did not resolve the dead letter.");
        }
        await onRefreshDashboard();
        await onRefreshIntegration();
        return "Destination repaired, replay executed, dead letter resolved.";
      });
      setResult({
        title: scenario.title,
        eventId: webhook?.event_id,
        deliveryId: delivery?.delivery_id,
        deadLetterId: deadLetter?.dead_letter_id,
        replayRequestId: replayRequest?.replay_request_id,
        summary:
          "Webhook received -> delivery rejected -> dead letter created -> replay requested -> approved -> replayed -> resolved.",
      });
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : "Guided scenario failed.";
      setError(message);
    }
  }

  async function runStep(index: number, action: () => Promise<string>) {
    updateStep(index, { status: "running" });
    try {
      const detail = await action();
      updateStep(index, { status: "completed", detail });
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Step failed.";
      updateStep(index, { status: "failed", detail });
      throw caught;
    }
  }

  function updateStep(index: number, patch: Partial<ScenarioStep>) {
    setSteps((current) =>
      current.map((step, stepIndex) =>
        stepIndex === index ? { ...step, ...patch } : step,
      ),
    );
  }

  async function ensureDestination(
    slug: string,
    scenario: ScenarioConfig,
  ): Promise<Destination> {
    const currentDestinations = await api.listDestinations(slug);
    const existing = currentDestinations.find(
      (destination) => destination.name === scenario.destinationName,
    );
    if (existing) {
      if (
        existing.endpoint_url !== scenario.destinationUrl ||
        existing.status !== "active"
      ) {
        return api.updateDestination(slug, existing.destination_id, {
          endpoint_url: scenario.destinationUrl,
          status: "active",
          configuration: { timeout_seconds: 10, max_attempts: 3 },
        });
      }
      return existing;
    }
    return api.createDestination(slug, {
      name: scenario.destinationName,
      destination_type: "http",
      endpoint_url: scenario.destinationUrl,
      timeout_seconds: 10,
      max_attempts: 3,
      status: "active",
    });
  }

  async function ensureRoutingRule(
    slug: string,
    scenario: ScenarioConfig,
    destination: Destination,
  ): Promise<RoutingRule> {
    const currentRules = await api.listRoutingRules(slug);
    const existing =
      currentRules.find((rule) => rule.name === scenario.ruleName) ??
      currentRules.find(
        (rule) =>
          rule.event_type === scenario.eventType &&
          rule.destination_id === destination.destination_id,
      );
    if (existing) {
      if (
        existing.destination_id !== destination.destination_id ||
        existing.event_type !== scenario.eventType ||
        existing.status !== "active" ||
        existing.priority !== 100
      ) {
        return api.updateRoutingRule(slug, existing.routing_rule_id, {
          destination_id: destination.destination_id,
          event_type: scenario.eventType,
          priority: 100,
          status: "active",
        });
      }
      return existing;
    }
    return api.createRoutingRule(slug, {
      name: scenario.ruleName,
      destination_id: destination.destination_id,
      event_type: scenario.eventType,
      priority: 100,
      status: "active",
    });
  }

  const isRunning = steps.some((step) => step.status === "running");

  return (
    <section className="rounded-lg border border-indigo-100 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
            Guided Mode
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            Run the RelayGuard lifecycle in one click
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            RelayGuard receives webhook events, protects them from being lost,
            routes them to destinations, retries temporary failures,
            dead-letters permanent failures, and helps operators replay failed
            deliveries. AI assistance is planned later for failure explanation
            and recovery suggestions.
          </p>
        </div>
        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          onClick={() => onNavigate("route-setup")}
          type="button"
        >
          Advanced setup
        </button>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-3">
        {SCENARIOS.map((scenario) => (
          <button
            className={`rounded-lg border p-4 text-left shadow-sm transition ${
              activeScenario === scenario.id
                ? "border-indigo-300 bg-indigo-50"
                : "border-slate-200 bg-white hover:border-indigo-200 hover:bg-indigo-50/50"
            }`}
            disabled={isRunning}
            key={scenario.id}
            onClick={() => void runScenario(scenario)}
            type="button"
          >
            <p className="font-semibold text-slate-950">{scenario.title}</p>
            <p className="mt-2 text-sm leading-5 text-slate-600">
              {scenario.purpose}
            </p>
            <p className="mt-3 font-mono text-xs text-slate-500">
              {scenario.eventType}
            </p>
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="text-sm font-semibold text-slate-900">
            Scenario timeline
          </p>
          {steps.length === 0 ? (
            <EmptyState
              title="No scenario running"
              message="Choose a scenario to watch RelayGuard perform the workflow."
            />
          ) : (
            <ol className="mt-3 grid gap-2">
              {steps.map((step, index) => (
                <li
                  className="rounded-md border border-slate-200 bg-white p-3"
                  key={`${step.label}-${index}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-900">
                      {index + 1}. {step.label}
                    </span>
                    <StatusBadge status={step.status} />
                  </div>
                  {step.detail ? (
                    <p className="mt-2 text-xs text-slate-500">{step.detail}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
        <DemoExplanation
          destinationNames={destinationNames}
          error={error}
          result={result}
        />
      </div>
    </section>
  );
}

function DemoExplanation({
  destinationNames,
  error,
  result,
}: {
  destinationNames: Map<string, string>;
  error: string | null;
  result: ScenarioResult | null;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-sm font-semibold text-slate-900">
        What just happened?
      </p>
      {error ? (
        <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </div>
      ) : null}
      {result ? (
        <div className="mt-3 space-y-3 text-sm text-slate-600">
          <p>{result.summary}</p>
          <div className="grid gap-2 text-xs">
            {result.eventId ? (
              <KeyValue label="Event" value={result.eventId} />
            ) : null}
            {result.deliveryId ? (
              <KeyValue label="Delivery" value={result.deliveryId} />
            ) : null}
            {result.deadLetterId ? (
              <KeyValue label="Dead letter" value={result.deadLetterId} />
            ) : null}
            {result.replayRequestId ? (
              <KeyValue label="Replay" value={result.replayRequestId} />
            ) : null}
          </div>
          <p>
            Why this matters: the operator can see every durable handoff instead
            of trusting a black-box webhook call.
          </p>
          <p>
            Next: inspect the manual Advanced Mode pages for the underlying
            event, delivery, attempts, retry jobs, dead letters, and replay
            requests.
          </p>
        </div>
      ) : (
        <div className="mt-3 space-y-3 text-sm text-slate-600">
          <p>
            These guided scenarios use real RelayGuard APIs and the local
            receiver on port 9000. Start the receiver before running delivery
            scenarios.
          </p>
          <p>
            Advanced Mode remains available for operators who want to configure
            destinations, routing rules, events, deliveries, and recovery
            manually.
          </p>
          {destinationNames.size > 0 ? (
            <p className="text-xs text-slate-500">
              Current destinations:{" "}
              {Array.from(destinationNames.values()).join(", ")}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="break-all font-mono text-slate-800">{value}</p>
    </div>
  );
}

function demoWebhook(scenario: ScenarioConfig) {
  const timestamp = Date.now();
  return {
    event_type: scenario.eventType,
    deduplication_key: `demo-${scenario.id}-${timestamp}`,
    source_event_id: `guided_${scenario.id}_${timestamp}`,
    payload: {
      invoice_id: `inv_${scenario.id}_${timestamp}`,
      customer_id: "cus_guided_demo",
      amount: 4200,
      currency: "USD",
      scenario: scenario.id,
      paid_at: new Date(timestamp).toISOString(),
    },
  };
}

function shortId(value: string) {
  return value.length > 12
    ? `${value.slice(0, 8)}...${value.slice(-4)}`
    : value;
}
