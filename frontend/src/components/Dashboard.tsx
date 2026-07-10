import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { api, ApiError } from "../lib/api";
import type {
  DeadLetter,
  Delivery,
  DeliveryAttempt,
  Destination,
  EventMetadata,
  Integration,
  ReplayRequest,
  RetryJob,
  RoutingRule,
  WebhookDraft,
  WebhookResult,
} from "../lib/types";
import { EventTester } from "./EventTester";
import { MetricCard } from "./MetricCard";
import { EmptyState, ErrorPanel, LoadingState } from "./States";
import { StatusBadge } from "./StatusBadge";

type HealthState = "checking" | "ok" | "unavailable";

type Toast = {
  tone: "success" | "warning" | "error";
  message: string;
};

const NAV_ITEMS = [
  "Overview",
  "Integrations",
  "Route setup",
  "Webhook tester",
  "Events",
  "Deliveries",
  "Recovery",
];

export function Dashboard() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [routingRules, setRoutingRules] = useState<RoutingRule[]>([]);
  const [events, setEvents] = useState<EventMetadata[]>([]);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [selectedDeliveryId, setSelectedDeliveryId] = useState("");
  const [attempts, setAttempts] = useState<DeliveryAttempt[]>([]);
  const [retryJobs, setRetryJobs] = useState<RetryJob[]>([]);
  const [deadLetters, setDeadLetters] = useState<DeadLetter[]>([]);
  const [selectedDeadLetterId, setSelectedDeadLetterId] = useState("");
  const [replayRequests, setReplayRequests] = useState<ReplayRequest[]>([]);
  const [recentWebhookResults, setRecentWebhookResults] = useState<
    WebhookResult[]
  >([]);
  const [destinationDraft, setDestinationDraft] = useState({
    name: "Billing Service",
    endpoint_url: "https://example.invalid/webhooks/billing",
    timeout_seconds: 10,
    max_attempts: 3,
  });
  const [ruleDraft, setRuleDraft] = useState({
    name: "Invoice paid to billing",
    event_type: "invoice.paid",
    priority: 100,
  });

  const selectedIntegration = integrations.find(
    (integration) => integration.slug === selectedSlug,
  );
  const selectedEvent = events.find(
    (event) => event.event_id === selectedEventId,
  );
  const selectedDelivery = deliveries.find(
    (delivery) => delivery.delivery_id === selectedDeliveryId,
  );
  const selectedDeadLetter = deadLetters.find(
    (deadLetter) => deadLetter.dead_letter_id === selectedDeadLetterId,
  );
  const activeReplayForDeadLetter = replayRequests.find(
    (request) =>
      request.dead_letter_id === selectedDeadLetterId &&
      ["pending", "approved", "running"].includes(request.status),
  );

  const metrics = useMemo(() => {
    const deliveryCounts = deliveries.reduce<Record<string, number>>(
      (counts, delivery) => {
        counts[delivery.status] = (counts[delivery.status] ?? 0) + 1;
        return counts;
      },
      {},
    );
    const replayCounts = replayRequests.reduce<Record<string, number>>(
      (counts, request) => {
        counts[request.status] = (counts[request.status] ?? 0) + 1;
        return counts;
      },
      {},
    );
    return {
      events: events.length,
      scheduled: deliveryCounts.scheduled ?? 0,
      delivered: deliveryCounts.delivered ?? 0,
      failed:
        (deliveryCounts.failed ?? 0) + (deliveryCounts.dead_lettered ?? 0),
      openDeadLetters: deadLetters.filter(
        (deadLetter) => deadLetter.resolution_status === "open",
      ).length,
      pendingReplays: replayCounts.pending ?? 0,
    };
  }, [deadLetters, deliveries, events, replayRequests]);

  useEffect(() => {
    void refreshDashboard();
  }, []);

  useEffect(() => {
    if (integrations.length > 0 && selectedSlug === "") {
      setSelectedSlug(integrations[0].slug);
    }
  }, [integrations, selectedSlug]);

  useEffect(() => {
    if (selectedSlug !== "") {
      void refreshIntegrationScopedData(selectedSlug);
    }
  }, [selectedSlug]);

  useEffect(() => {
    if (events.length > 0 && selectedEventId === "") {
      setSelectedEventId(events[0].event_id);
    }
  }, [events, selectedEventId]);

  useEffect(() => {
    if (selectedEventId !== "") {
      void refreshEventData(selectedEventId);
    }
  }, [selectedEventId]);

  useEffect(() => {
    if (deliveries.length > 0 && selectedDeliveryId === "") {
      setSelectedDeliveryId(deliveries[0].delivery_id);
    }
  }, [deliveries, selectedDeliveryId]);

  useEffect(() => {
    if (selectedDeliveryId !== "") {
      void refreshDeliveryData(selectedDeliveryId);
    }
  }, [selectedDeliveryId]);

  useEffect(() => {
    if (deadLetters.length > 0 && selectedDeadLetterId === "") {
      setSelectedDeadLetterId(deadLetters[0].dead_letter_id);
    }
  }, [deadLetters, selectedDeadLetterId]);

  async function refreshDashboard() {
    setLoading(true);
    setError(null);
    try {
      await api.health();
      setHealth("ok");
    } catch {
      setHealth("unavailable");
      setError(
        "Backend is unavailable. Start FastAPI on port 8000 and refresh the dashboard.",
      );
      setLoading(false);
      return;
    }

    try {
      const [integrationData, eventData, deadLetterData, replayData] =
        await Promise.all([
          api.listIntegrations(),
          api.listEvents(),
          api.listDeadLetters(),
          api.listReplayRequests(),
        ]);
      setIntegrations(integrationData);
      setEvents(eventData);
      setDeadLetters(deadLetterData);
      setReplayRequests(replayData);
      if (integrationData.length > 0) {
        setSelectedSlug((current) => current || integrationData[0].slug);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  async function refreshIntegrationScopedData(slug: string) {
    try {
      const [destinationData, ruleData, eventData] = await Promise.all([
        api.listDestinations(slug),
        api.listRoutingRules(slug),
        api.listEvents(slug),
      ]);
      setDestinations(destinationData);
      setRoutingRules(ruleData);
      setEvents(eventData);
      setSelectedEventId(eventData[0]?.event_id ?? "");
      setDeliveries([]);
      setSelectedDeliveryId("");
      setAttempts([]);
      setRetryJobs([]);
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function refreshEventData(eventId: string) {
    try {
      const deliveryData = await api.listDeliveries(eventId);
      setDeliveries(deliveryData);
      setSelectedDeliveryId(deliveryData[0]?.delivery_id ?? "");
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function refreshDeliveryData(deliveryId: string) {
    try {
      const [attemptData, retryData] = await Promise.all([
        api.listDeliveryAttempts(deliveryId),
        api.listRetryJobs(deliveryId),
      ]);
      setAttempts(attemptData);
      setRetryJobs(retryData);
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function refreshRecoveryData() {
    const [deadLetterData, replayData] = await Promise.all([
      api.listDeadLetters(),
      api.listReplayRequests(),
    ]);
    setDeadLetters(deadLetterData);
    setReplayRequests(replayData);
  }

  async function setIntegrationStatus(status: "active" | "disabled") {
    if (!selectedIntegration) {
      return;
    }
    try {
      const updated = await api.updateIntegration(
        selectedIntegration.slug,
        status,
      );
      setIntegrations((current) =>
        current.map((integration) =>
          integration.slug === updated.slug ? updated : integration,
        ),
      );
      setToast({
        tone: "success",
        message: `${updated.name} is now ${updated.status}.`,
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function createDestination(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSlug) {
      return;
    }
    try {
      await api.createDestination(selectedSlug, {
        name: destinationDraft.name,
        destination_type: "http",
        endpoint_url: destinationDraft.endpoint_url,
        timeout_seconds: destinationDraft.timeout_seconds,
        max_attempts: destinationDraft.max_attempts,
        status: "active",
      });
      await refreshIntegrationScopedData(selectedSlug);
      setToast({ tone: "success", message: "Destination created." });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function createRoutingRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSlug || destinations.length === 0) {
      return;
    }
    try {
      await api.createRoutingRule(selectedSlug, {
        name: ruleDraft.name,
        destination_id: destinations[0].destination_id,
        event_type: ruleDraft.event_type,
        priority: ruleDraft.priority,
        status: "active",
      });
      await refreshIntegrationScopedData(selectedSlug);
      setToast({ tone: "success", message: "Routing rule created." });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function submitWebhook(draft: WebhookDraft) {
    if (!selectedSlug) {
      return;
    }
    try {
      const result = await api.submitWebhook(selectedSlug, draft);
      setRecentWebhookResults((current) => [result, ...current].slice(0, 5));
      const eventData = await api.listEvents(selectedSlug);
      setEvents(eventData);
      setSelectedEventId(result.event_id);
      setToast({
        tone: result.duplicate ? "warning" : "success",
        message: result.duplicate
          ? "Duplicate webhook mapped to the original event."
          : "Webhook accepted.",
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function scheduleSelectedEvent() {
    if (!selectedEventId) {
      return;
    }
    try {
      const result = await api.scheduleDeliveries(selectedEventId);
      await refreshEventData(selectedEventId);
      setToast({
        tone: "success",
        message: `Scheduled ${result.scheduled_count}; already scheduled ${result.already_scheduled_count}.`,
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function executeSelectedDelivery() {
    if (!selectedDeliveryId) {
      return;
    }
    try {
      const result = await api.executeDelivery(selectedDeliveryId);
      if (selectedEventId) {
        await refreshEventData(selectedEventId);
      }
      await refreshDeliveryData(selectedDeliveryId);
      await refreshRecoveryData();
      setToast({
        tone: result.dead_lettered ? "warning" : "success",
        message: `Delivery execution finished with status ${result.status}.`,
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function executeRetryJob(retryJobId: string) {
    try {
      const result = await api.executeRetryJob(retryJobId);
      await refreshDeliveryData(result.delivery_id);
      await refreshRecoveryData();
      setToast({
        tone: "success",
        message: `Retry job ${result.retry_status}.`,
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function createReplayRequest() {
    if (!selectedDeadLetterId) {
      return;
    }
    try {
      await api.createReplayRequest(
        selectedDeadLetterId,
        "Downstream service has recovered; replay requested from the dashboard.",
        "dashboard-operator",
      );
      await refreshRecoveryData();
      setToast({ tone: "success", message: "Replay request created." });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function approveReplayRequest() {
    if (!activeReplayForDeadLetter) {
      return;
    }
    try {
      await api.approveReplayRequest(
        activeReplayForDeadLetter.replay_request_id,
        "dashboard-operator",
        "Approved from the operator dashboard.",
      );
      await refreshRecoveryData();
      setToast({ tone: "success", message: "Replay request approved." });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function rejectReplayRequest() {
    if (!activeReplayForDeadLetter) {
      return;
    }
    try {
      await api.rejectReplayRequest(
        activeReplayForDeadLetter.replay_request_id,
        "dashboard-operator",
        "Rejected from the operator dashboard.",
      );
      await refreshRecoveryData();
      setToast({ tone: "warning", message: "Replay request rejected." });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function executeReplayRequest() {
    if (!activeReplayForDeadLetter) {
      return;
    }
    try {
      const result = await api.executeReplayRequest(
        activeReplayForDeadLetter.replay_request_id,
      );
      await refreshRecoveryData();
      if (selectedDeliveryId) {
        await refreshDeliveryData(selectedDeliveryId);
      }
      setToast({
        tone: result.dead_letter_resolved ? "success" : "warning",
        message: `Replay ${result.replay_status}; delivery is ${result.delivery_status}.`,
      });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  return (
    <main className="min-h-screen bg-stone-950 text-stone-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 border-r border-stone-800 bg-stone-950/95 px-5 py-6 lg:block">
          <p className="text-lg font-bold text-white">RelayGuard</p>
          <p className="mt-1 text-sm text-stone-400">Operator Dashboard MVP</p>
          <nav className="mt-8 grid gap-1">
            {NAV_ITEMS.map((item) => (
              <a
                className="rounded-md px-3 py-2 text-sm font-medium text-stone-300 transition hover:bg-stone-900 hover:text-white"
                href={`#${item.toLowerCase().replaceAll(" ", "-")}`}
                key={item}
              >
                {item}
              </a>
            ))}
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-10 border-b border-stone-800 bg-stone-950/90 px-4 py-4 backdrop-blur md:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-cyan-200">
                  RelayGuard
                </p>
                <h1 className="text-2xl font-bold text-white md:text-3xl">
                  Reliability lifecycle command center
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge status={health === "ok" ? "active" : health} />
                <select
                  className="max-w-full rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-sm text-stone-100"
                  onChange={(event) => setSelectedSlug(event.target.value)}
                  value={selectedSlug}
                >
                  {integrations.length === 0 ? (
                    <option value="">No integrations</option>
                  ) : null}
                  {integrations.map((integration) => (
                    <option key={integration.slug} value={integration.slug}>
                      {integration.slug}
                    </option>
                  ))}
                </select>
                <button
                  className="rounded-md border border-stone-700 px-3 py-2 text-sm font-semibold text-stone-200 transition hover:border-cyan-300 hover:text-white"
                  onClick={() => void refreshDashboard()}
                  type="button"
                >
                  Refresh
                </button>
              </div>
            </div>
          </header>

          <div className="space-y-6 px-4 py-6 md:px-8">
            {toast ? (
              <ToastPanel toast={toast} onDismiss={() => setToast(null)} />
            ) : null}
            {error ? (
              <ErrorPanel title="Dashboard needs the backend" message={error} />
            ) : null}
            {loading ? (
              <LoadingState label="Loading RelayGuard API state..." />
            ) : null}

            <Section id="overview" title="Overview">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  label="Recent events"
                  value={metrics.events}
                  helper="Safe metadata rows"
                />
                <MetricCard
                  label="Scheduled"
                  value={metrics.scheduled}
                  helper="Deliveries waiting"
                  tone="amber"
                />
                <MetricCard
                  label="Delivered"
                  value={metrics.delivered}
                  helper="Completed deliveries"
                  tone="emerald"
                />
                <MetricCard
                  label="Recovery"
                  value={metrics.openDeadLetters}
                  helper={`${metrics.pendingReplays} pending replay requests`}
                  tone={metrics.failed > 0 ? "rose" : "cyan"}
                />
              </div>
              <DemoGuide />
            </Section>

            <Section id="integrations" title="Integrations">
              <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <Panel title="Available integrations">
                  {integrations.length === 0 ? (
                    <EmptyState
                      title="No integrations yet"
                      message="Run the backend seed command to create sandbox integrations."
                    />
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] text-left text-sm">
                        <thead className="text-xs uppercase text-stone-500">
                          <tr>
                            <th className="py-2 pr-3">Name</th>
                            <th className="py-2 pr-3">Slug</th>
                            <th className="py-2 pr-3">Status</th>
                            <th className="py-2 pr-3">Updated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-800">
                          {integrations.map((integration) => (
                            <tr
                              className="cursor-pointer hover:bg-stone-900"
                              key={integration.integration_id}
                              onClick={() => setSelectedSlug(integration.slug)}
                            >
                              <td className="py-3 pr-3 font-medium text-stone-100">
                                {integration.name}
                              </td>
                              <td className="py-3 pr-3 text-stone-400">
                                {integration.slug}
                              </td>
                              <td className="py-3 pr-3">
                                <StatusBadge status={integration.status} />
                              </td>
                              <td className="py-3 pr-3 text-stone-400">
                                {formatDate(integration.updated_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Panel>
                <Panel title="Selected integration">
                  {selectedIntegration ? (
                    <div className="space-y-4">
                      <div>
                        <p className="text-sm text-stone-400">Slug</p>
                        <p className="font-mono text-sm text-stone-100">
                          {selectedIntegration.slug}
                        </p>
                      </div>
                      <StatusBadge status={selectedIntegration.status} />
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded-md bg-emerald-300 px-3 py-2 text-sm font-semibold text-stone-950"
                          onClick={() => void setIntegrationStatus("active")}
                          type="button"
                        >
                          Activate
                        </button>
                        <button
                          className="rounded-md border border-stone-700 px-3 py-2 text-sm font-semibold text-stone-200"
                          onClick={() => void setIntegrationStatus("disabled")}
                          type="button"
                        >
                          Disable
                        </button>
                      </div>
                    </div>
                  ) : (
                    <EmptyState
                      title="Select an integration"
                      message="Seed data creates demo integrations."
                    />
                  )}
                </Panel>
              </div>
            </Section>

            <Section id="route-setup" title="Destination and routing">
              <div className="grid gap-4 xl:grid-cols-2">
                <Panel title="Create destination">
                  <form
                    className="grid gap-3"
                    onSubmit={(event) => void createDestination(event)}
                  >
                    <TextInput
                      label="Name"
                      onChange={(value) =>
                        setDestinationDraft((current) => ({
                          ...current,
                          name: value,
                        }))
                      }
                      value={destinationDraft.name}
                    />
                    <TextInput
                      label="Endpoint URL"
                      onChange={(value) =>
                        setDestinationDraft((current) => ({
                          ...current,
                          endpoint_url: value,
                        }))
                      }
                      value={destinationDraft.endpoint_url}
                    />
                    <div className="grid gap-3 md:grid-cols-2">
                      <NumberInput
                        label="Timeout seconds"
                        onChange={(value) =>
                          setDestinationDraft((current) => ({
                            ...current,
                            timeout_seconds: value,
                          }))
                        }
                        value={destinationDraft.timeout_seconds}
                      />
                      <NumberInput
                        label="Max attempts"
                        onChange={(value) =>
                          setDestinationDraft((current) => ({
                            ...current,
                            max_attempts: value,
                          }))
                        }
                        value={destinationDraft.max_attempts}
                      />
                    </div>
                    <PrimaryButton disabled={!selectedSlug}>
                      Create destination
                    </PrimaryButton>
                  </form>
                </Panel>
                <Panel title="Create routing rule">
                  <form
                    className="grid gap-3"
                    onSubmit={(event) => void createRoutingRule(event)}
                  >
                    <TextInput
                      label="Name"
                      onChange={(value) =>
                        setRuleDraft((current) => ({ ...current, name: value }))
                      }
                      value={ruleDraft.name}
                    />
                    <TextInput
                      label="Event type"
                      onChange={(value) =>
                        setRuleDraft((current) => ({
                          ...current,
                          event_type: value,
                        }))
                      }
                      value={ruleDraft.event_type}
                    />
                    <NumberInput
                      label="Priority"
                      onChange={(value) =>
                        setRuleDraft((current) => ({
                          ...current,
                          priority: value,
                        }))
                      }
                      value={ruleDraft.priority}
                    />
                    <PrimaryButton
                      disabled={!selectedSlug || destinations.length === 0}
                    >
                      Create routing rule
                    </PrimaryButton>
                  </form>
                </Panel>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <ResourceList
                  empty="Create a destination to receive scheduled deliveries."
                  items={destinations.map((destination) => ({
                    id: destination.destination_id,
                    title: destination.name,
                    subtitle: destination.endpoint_url,
                    status: destination.status,
                  }))}
                  title="Destinations"
                />
                <ResourceList
                  empty="Create a routing rule to match accepted event types."
                  items={routingRules.map((rule) => ({
                    id: rule.routing_rule_id,
                    title: rule.name,
                    subtitle: `${rule.event_type} -> ${shortId(rule.destination_id)}`,
                    status: rule.status,
                  }))}
                  title="Routing rules"
                />
              </div>
            </Section>

            <Section id="webhook-tester" title="Webhook event tester">
              <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
                <Panel title="Submit demo event">
                  <EventTester
                    disabled={
                      !selectedIntegration ||
                      selectedIntegration.status !== "active"
                    }
                    onSubmit={submitWebhook}
                  />
                </Panel>
                <Panel title="Recent submissions">
                  {recentWebhookResults.length === 0 ? (
                    <EmptyState
                      title="No demo webhooks submitted"
                      message="Activate an integration, create a route, and submit an event."
                    />
                  ) : (
                    <div className="grid gap-3">
                      {recentWebhookResults.map((result) => (
                        <button
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3 text-left transition hover:border-cyan-300"
                          key={result.receipt_id}
                          onClick={() => setSelectedEventId(result.event_id)}
                          type="button"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-xs text-stone-300">
                              {shortId(result.event_id)}
                            </span>
                            <StatusBadge
                              status={
                                result.duplicate ? "duplicate" : result.status
                              }
                            />
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>
            </Section>

            <Section id="events" title="Events">
              <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <Panel title="Recent event metadata">
                  {events.length === 0 ? (
                    <EmptyState
                      title="No recent events"
                      message="Submit a webhook to create a canonical event."
                    />
                  ) : (
                    <div className="grid gap-2">
                      {events.map((event) => (
                        <button
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3 text-left transition hover:border-cyan-300"
                          key={event.event_id}
                          onClick={() => setSelectedEventId(event.event_id)}
                          type="button"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="font-medium text-stone-100">
                                {event.event_type}
                              </p>
                              <p className="font-mono text-xs text-stone-500">
                                {shortId(event.event_id)}
                              </p>
                            </div>
                            <StatusBadge status={event.status} />
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </Panel>
                <Panel title="Event detail">
                  {selectedEvent ? (
                    <div className="space-y-4">
                      <KeyValue
                        label="Event ID"
                        value={selectedEvent.event_id}
                      />
                      <KeyValue
                        label="Integration ID"
                        value={selectedEvent.integration_id}
                      />
                      <KeyValue
                        label="Source event"
                        value={selectedEvent.source_event_id ?? "null"}
                      />
                      <KeyValue
                        label="Accepted"
                        value={formatDate(selectedEvent.accepted_at)}
                      />
                      <StatusBadge status={selectedEvent.status} />
                      <PrimaryButton
                        disabled={selectedEvent.status !== "accepted"}
                        onClick={scheduleSelectedEvent}
                      >
                        Schedule deliveries
                      </PrimaryButton>
                    </div>
                  ) : (
                    <EmptyState
                      title="No event selected"
                      message="Choose an event to inspect metadata."
                    />
                  )}
                </Panel>
              </div>
            </Section>

            <Section id="deliveries" title="Deliveries">
              <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
                <Panel title="Delivery records">
                  {deliveries.length === 0 ? (
                    <EmptyState
                      title="No deliveries"
                      message="Schedule deliveries for an accepted event."
                    />
                  ) : (
                    <div className="grid gap-2">
                      {deliveries.map((delivery) => (
                        <button
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3 text-left transition hover:border-cyan-300"
                          key={delivery.delivery_id}
                          onClick={() =>
                            setSelectedDeliveryId(delivery.delivery_id)
                          }
                          type="button"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <span className="font-mono text-xs text-stone-300">
                              {shortId(delivery.delivery_id)}
                            </span>
                            <StatusBadge status={delivery.status} />
                          </div>
                          <p className="mt-2 text-xs text-stone-500">
                            attempts {delivery.attempt_count} · next{" "}
                            {delivery.next_attempt_at
                              ? formatDate(delivery.next_attempt_at)
                              : "none"}
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </Panel>
                <Panel title="Delivery detail">
                  {selectedDelivery ? (
                    <div className="space-y-4">
                      <KeyValue
                        label="Delivery ID"
                        value={selectedDelivery.delivery_id}
                      />
                      <KeyValue
                        label="Destination ID"
                        value={selectedDelivery.destination_id}
                      />
                      <KeyValue
                        label="Routing rule ID"
                        value={selectedDelivery.routing_rule_id ?? "manual"}
                      />
                      <StatusBadge status={selectedDelivery.status} />
                      <PrimaryButton
                        disabled={
                          !["scheduled", "failed"].includes(
                            selectedDelivery.status,
                          )
                        }
                        onClick={executeSelectedDelivery}
                      >
                        Execute delivery
                      </PrimaryButton>
                    </div>
                  ) : (
                    <EmptyState
                      title="No delivery selected"
                      message="Choose a delivery record."
                    />
                  )}
                </Panel>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <Panel title="Attempts">
                  {attempts.length === 0 ? (
                    <EmptyState
                      title="No attempts"
                      message="Execute a delivery to record attempts."
                    />
                  ) : (
                    <div className="grid gap-2">
                      {attempts.map((attempt) => (
                        <div
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3"
                          key={attempt.attempt_id}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm font-medium">
                              Attempt {attempt.attempt_number}
                            </span>
                            <StatusBadge status={attempt.outcome} />
                          </div>
                          <p className="mt-2 text-xs text-stone-500">
                            {attempt.response_status_code ??
                              attempt.error_code ??
                              "no status"}{" "}
                            · {attempt.error_message ?? "no error"}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
                <Panel title="Retry jobs">
                  {retryJobs.length === 0 ? (
                    <EmptyState
                      title="No retry jobs"
                      message="Retryable failures create pending jobs."
                    />
                  ) : (
                    <div className="grid gap-2">
                      {retryJobs.map((job) => (
                        <div
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3"
                          key={job.retry_job_id}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <span className="font-mono text-xs">
                              {shortId(job.retry_job_id)}
                            </span>
                            <StatusBadge status={job.status} />
                          </div>
                          <p className="mt-2 text-xs text-stone-500">
                            run at {formatDate(job.run_at)}
                          </p>
                          <button
                            className="mt-3 rounded-md border border-stone-700 px-3 py-2 text-xs font-semibold text-stone-200 disabled:cursor-not-allowed disabled:text-stone-600"
                            disabled={job.status !== "pending"}
                            onClick={() =>
                              void executeRetryJob(job.retry_job_id)
                            }
                            type="button"
                          >
                            Execute retry
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>
            </Section>

            <Section id="recovery" title="Dead letters and replay">
              <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
                <Panel title="Dead letters">
                  {deadLetters.length === 0 ? (
                    <EmptyState
                      title="No dead letters"
                      message="Terminal delivery failures will appear here."
                    />
                  ) : (
                    <div className="grid gap-2">
                      {deadLetters.map((deadLetter) => (
                        <button
                          className="rounded-lg border border-stone-800 bg-stone-950 p-3 text-left transition hover:border-cyan-300"
                          key={deadLetter.dead_letter_id}
                          onClick={() =>
                            setSelectedDeadLetterId(deadLetter.dead_letter_id)
                          }
                          type="button"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <span className="font-mono text-xs">
                              {shortId(deadLetter.dead_letter_id)}
                            </span>
                            <StatusBadge
                              status={deadLetter.resolution_status}
                            />
                          </div>
                          <p className="mt-2 text-xs text-stone-500">
                            {deadLetter.reason_code} ·{" "}
                            {deadLetter.reason_message}
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </Panel>
                <Panel title="Replay workflow">
                  {selectedDeadLetter ? (
                    <div className="space-y-4">
                      <KeyValue
                        label="Dead letter ID"
                        value={selectedDeadLetter.dead_letter_id}
                      />
                      <KeyValue
                        label="Delivery ID"
                        value={selectedDeadLetter.delivery_id}
                      />
                      <StatusBadge
                        status={selectedDeadLetter.resolution_status}
                      />
                      {activeReplayForDeadLetter ? (
                        <div className="rounded-lg border border-stone-800 bg-stone-950 p-3">
                          <p className="text-sm font-medium text-stone-100">
                            Active replay
                          </p>
                          <p className="mt-1 font-mono text-xs text-stone-500">
                            {shortId(
                              activeReplayForDeadLetter.replay_request_id,
                            )}
                          </p>
                          <div className="mt-3">
                            <StatusBadge
                              status={activeReplayForDeadLetter.status}
                            />
                          </div>
                        </div>
                      ) : null}
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded-md bg-cyan-300 px-3 py-2 text-sm font-semibold text-stone-950 disabled:bg-stone-700 disabled:text-stone-400"
                          disabled={
                            selectedDeadLetter.resolution_status ===
                              "resolved" ||
                            activeReplayForDeadLetter !== undefined
                          }
                          onClick={() => void createReplayRequest()}
                          type="button"
                        >
                          Create replay
                        </button>
                        <button
                          className="rounded-md border border-stone-700 px-3 py-2 text-sm font-semibold text-stone-200 disabled:text-stone-600"
                          disabled={
                            activeReplayForDeadLetter?.status !== "pending"
                          }
                          onClick={() => void approveReplayRequest()}
                          type="button"
                        >
                          Approve
                        </button>
                        <button
                          className="rounded-md border border-stone-700 px-3 py-2 text-sm font-semibold text-stone-200 disabled:text-stone-600"
                          disabled={
                            activeReplayForDeadLetter === undefined ||
                            !["pending", "approved"].includes(
                              activeReplayForDeadLetter.status,
                            )
                          }
                          onClick={() => void rejectReplayRequest()}
                          type="button"
                        >
                          Reject
                        </button>
                        <button
                          className="rounded-md bg-emerald-300 px-3 py-2 text-sm font-semibold text-stone-950 disabled:bg-stone-700 disabled:text-stone-400"
                          disabled={
                            activeReplayForDeadLetter?.status !== "approved"
                          }
                          onClick={() => void executeReplayRequest()}
                          type="button"
                        >
                          Execute replay
                        </button>
                      </div>
                    </div>
                  ) : (
                    <EmptyState
                      title="No dead letter selected"
                      message="Choose a dead letter to recover."
                    />
                  )}
                </Panel>
              </div>
              <ResourceList
                empty="Replay requests appear after an operator creates one."
                items={replayRequests.map((request) => ({
                  id: request.replay_request_id,
                  title: request.reason ?? "Replay request",
                  subtitle: `${shortId(request.dead_letter_id)} · ${request.requested_by ?? "unknown"}`,
                  status: request.status,
                }))}
                title="Replay requests"
              />
            </Section>
          </div>
        </div>
      </div>
    </main>
  );
}

function Section({
  children,
  id,
  title,
}: {
  children: ReactNode;
  id: string;
  title: string;
}) {
  return (
    <section className="scroll-mt-24 space-y-4" id={id}>
      <h2 className="text-xl font-bold text-white">{title}</h2>
      {children}
    </section>
  );
}

function Panel({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="rounded-lg border border-stone-800 bg-stone-900/70 p-4 shadow-xl shadow-black/20">
      <h3 className="mb-4 text-sm font-semibold uppercase text-stone-400">
        {title}
      </h3>
      {children}
    </div>
  );
}

function DemoGuide() {
  const steps = [
    "Start backend and frontend",
    "Activate a sandbox integration",
    "Create destination and routing rule",
    "Submit a demo webhook",
    "Schedule and execute delivery",
    "Inspect attempts, dead letters, and replay",
  ];
  return (
    <Panel title="How to demo locally">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {steps.map((step, index) => (
          <div
            className="rounded-md border border-stone-800 bg-stone-950 p-3"
            key={step}
          >
            <p className="text-xs font-semibold text-cyan-200">
              Step {index + 1}
            </p>
            <p className="mt-1 text-sm text-stone-200">{step}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ResourceList({
  empty,
  items,
  title,
}: {
  empty: string;
  items: Array<{ id: string; title: string; subtitle: string; status: string }>;
  title: string;
}) {
  return (
    <Panel title={title}>
      {items.length === 0 ? (
        <EmptyState title="Nothing here yet" message={empty} />
      ) : (
        <div className="grid gap-2">
          {items.map((item) => (
            <div
              className="rounded-lg border border-stone-800 bg-stone-950 p-3"
              key={item.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="font-medium text-stone-100">{item.title}</p>
                <StatusBadge status={item.status} />
              </div>
              <p className="mt-2 text-xs text-stone-500">{item.subtitle}</p>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function TextInput({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-stone-200">{label}</span>
      <input
        className="rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-stone-100 outline-none focus:border-cyan-300"
        onChange={(event) => onChange(event.target.value)}
        required
        value={value}
      />
    </label>
  );
}

function NumberInput({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: number) => void;
  value: number;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-stone-200">{label}</span>
      <input
        className="rounded-md border border-stone-700 bg-stone-950 px-3 py-2 text-stone-100 outline-none focus:border-cyan-300"
        min={1}
        onChange={(event) => onChange(Number(event.target.value))}
        required
        type="number"
        value={value}
      />
    </label>
  );
}

function PrimaryButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      className="rounded-md bg-cyan-300 px-4 py-2 text-sm font-semibold text-stone-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-stone-700 disabled:text-stone-400"
      disabled={disabled}
      onClick={onClick ? () => onClick() : undefined}
      type={onClick ? "button" : "submit"}
    >
      {children}
    </button>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-stone-500">{label}</p>
      <p className="mt-1 break-all font-mono text-sm text-stone-100">{value}</p>
    </div>
  );
}

function ToastPanel({
  onDismiss,
  toast,
}: {
  onDismiss: () => void;
  toast: Toast;
}) {
  const tone = {
    error: "border-rose-400/35 bg-rose-950/60 text-rose-100",
    success: "border-emerald-400/35 bg-emerald-950/60 text-emerald-100",
    warning: "border-amber-400/35 bg-amber-950/60 text-amber-100",
  }[toast.tone];
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-lg border p-3 text-sm ${tone}`}
    >
      <p>{toast.message}</p>
      <button
        className="font-semibold text-white"
        onClick={onDismiss}
        type="button"
      >
        Dismiss
      </button>
    </div>
  );
}

function shortId(value: string) {
  return value.length > 12
    ? `${value.slice(0, 8)}...${value.slice(-4)}`
    : value;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function errorMessage(caught: unknown) {
  if (caught instanceof ApiError) {
    return caught.message;
  }
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Unexpected dashboard error.";
}
