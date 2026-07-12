import { useEffect, useMemo, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";

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
import { GuidedDemo } from "./GuidedDemo";
import { MetricCard } from "./MetricCard";
import { EmptyState, ErrorPanel, LoadingState } from "./States";
import { StatusBadge } from "./StatusBadge";

type HealthState = "checking" | "ok" | "unavailable";
type PageKey =
  | "overview"
  | "integrations"
  | "route-setup"
  | "webhook-tester"
  | "events"
  | "deliveries"
  | "recovery";

type Toast = {
  tone: "success" | "warning" | "error";
  message: string;
};

const NAV_ITEMS: Array<{ key: PageKey; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "integrations", label: "Integrations" },
  { key: "route-setup", label: "Route Setup" },
  { key: "webhook-tester", label: "Webhook Tester" },
  { key: "events", label: "Events" },
  { key: "deliveries", label: "Deliveries" },
  { key: "recovery", label: "Recovery" },
];
const DEMO_RECEIVER_URLS = [
  {
    label: "Success",
    url: "http://127.0.0.1:9000/success",
    helper: "Returns 200 and marks delivery delivered.",
  },
  {
    label: "Retryable fail",
    url: "http://127.0.0.1:9000/fail",
    helper: "Returns 503 and creates a retry job.",
  },
  {
    label: "Reject",
    url: "http://127.0.0.1:9000/reject",
    helper: "Returns 400 and dead-letters the delivery.",
  },
  {
    label: "Slow",
    url: "http://127.0.0.1:9000/slow",
    helper: "Sleeps before responding to exercise timeouts.",
  },
];

export function Dashboard() {
  const [activePage, setActivePage] = useState<PageKey>("overview");
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
    destination_id: "",
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

  const recentActivity = useMemo(() => {
    const eventRows = events.map((event) => ({
      id: event.event_id,
      label: event.event_type,
      meta: `event ${shortId(event.event_id)}`,
      status: event.status,
      at: event.accepted_at,
    }));
    const deadLetterRows = deadLetters.map((deadLetter) => ({
      id: deadLetter.dead_letter_id,
      label: deadLetter.reason_code,
      meta: `dead letter ${shortId(deadLetter.dead_letter_id)}`,
      status: deadLetter.resolution_status,
      at: deadLetter.dead_lettered_at,
    }));
    const replayRows = replayRequests.map((request) => ({
      id: request.replay_request_id,
      label: request.reason ?? "Replay request",
      meta: `replay ${shortId(request.replay_request_id)}`,
      status: request.status,
      at: request.updated_at,
    }));
    return [...eventRows, ...deadLetterRows, ...replayRows]
      .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
      .slice(0, 6);
  }, [deadLetters, events, replayRequests]);

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
      const [
        integrationData,
        eventData,
        deliveryData,
        deadLetterData,
        replayData,
      ] = await Promise.all([
        api.listIntegrations(),
        api.listEvents(),
        api.listRecentDeliveries(),
        api.listDeadLetters(),
        api.listReplayRequests(),
      ]);
      setIntegrations(integrationData);
      setEvents(eventData);
      setDeliveries(deliveryData);
      setDeadLetters(deadLetterData);
      setReplayRequests(replayData);
      setSelectedDeliveryId((current) =>
        deliveryData.some((delivery) => delivery.delivery_id === current)
          ? current
          : (deliveryData[0]?.delivery_id ?? ""),
      );
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
      setRuleDraft((current) => ({
        ...current,
        destination_id: destinationData.some(
          (destination) =>
            destination.destination_id === current.destination_id,
        )
          ? current.destination_id
          : (destinationData[0]?.destination_id ?? ""),
      }));
      setSelectedEventId(eventData[0]?.event_id ?? "");
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function refreshRecentDeliveries(preferredDeliveryId?: string) {
    const deliveryData = await api.listRecentDeliveries();
    setDeliveries(deliveryData);
    setSelectedDeliveryId((current) => {
      if (
        preferredDeliveryId &&
        deliveryData.some(
          (delivery) => delivery.delivery_id === preferredDeliveryId,
        )
      ) {
        return preferredDeliveryId;
      }
      if (deliveryData.some((delivery) => delivery.delivery_id === current)) {
        return current;
      }
      return deliveryData[0]?.delivery_id ?? "";
    });
  }

  async function refreshEventData(eventId: string) {
    try {
      const deliveryData = await api.listDeliveries(eventId);
      setDeliveries((current) => mergeDeliveries(deliveryData, current));
      if (deliveryData.length > 0) {
        setSelectedDeliveryId((current) =>
          deliveryData.some((delivery) => delivery.delivery_id === current)
            ? current
            : deliveryData[0].delivery_id,
        );
      }
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
    if (!selectedSlug || ruleDraft.destination_id === "") {
      return;
    }
    try {
      await api.createRoutingRule(selectedSlug, {
        name: ruleDraft.name,
        destination_id: ruleDraft.destination_id,
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

  async function updateDestinationStatus(
    destinationId: string,
    status: "active" | "disabled",
  ) {
    if (!selectedSlug) {
      return;
    }
    try {
      await api.updateDestination(selectedSlug, destinationId, { status });
      await refreshIntegrationScopedData(selectedSlug);
      setToast({ tone: "success", message: `Destination ${status}.` });
    } catch (caught) {
      setToast({ tone: "error", message: errorMessage(caught) });
    }
  }

  async function updateRoutingRuleStatus(
    routingRuleId: string,
    status: "active" | "disabled",
  ) {
    if (!selectedSlug) {
      return;
    }
    try {
      await api.updateRoutingRule(selectedSlug, routingRuleId, { status });
      await refreshIntegrationScopedData(selectedSlug);
      setToast({ tone: "success", message: `Routing rule ${status}.` });
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
      await refreshRecentDeliveries();
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
      await refreshRecentDeliveries(selectedDeliveryId);
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
      await refreshRecentDeliveries(result.delivery_id);
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
      await refreshRecentDeliveries(result.delivery_id);
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
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <div className="min-h-screen pl-64 lg:pl-72">
        <TopHeader
          health={health}
          integrations={integrations}
          onRefresh={() => void refreshDashboard()}
          onSelectIntegration={setSelectedSlug}
          selectedSlug={selectedSlug}
        />
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {toast ? (
            <ToastPanel toast={toast} onDismiss={() => setToast(null)} />
          ) : null}
          {error ? (
            <ErrorPanel title="Dashboard needs the backend" message={error} />
          ) : null}
          {loading ? (
            <LoadingState label="Loading RelayGuard API state..." />
          ) : null}
          <PageHeader
            activePage={activePage}
            selectedIntegration={selectedIntegration}
          />
          {renderActivePage()}
        </div>
      </div>
    </main>
  );

  function renderActivePage() {
    switch (activePage) {
      case "integrations":
        return (
          <IntegrationsPage
            integrations={integrations}
            onSelect={setSelectedSlug}
            onSetStatus={setIntegrationStatus}
            selectedIntegration={selectedIntegration}
          />
        );
      case "route-setup":
        return (
          <RouteSetupPage
            createDestination={createDestination}
            createRoutingRule={createRoutingRule}
            destinationDraft={destinationDraft}
            destinations={destinations}
            routingRules={routingRules}
            ruleDraft={ruleDraft}
            selectedSlug={selectedSlug}
            setDestinationDraft={setDestinationDraft}
            setRuleDraft={setRuleDraft}
            updateDestinationStatus={updateDestinationStatus}
            updateRoutingRuleStatus={updateRoutingRuleStatus}
          />
        );
      case "webhook-tester":
        return (
          <WebhookTesterPage
            onSubmit={submitWebhook}
            recentWebhookResults={recentWebhookResults}
            selectedIntegration={selectedIntegration}
            setActivePage={setActivePage}
            setSelectedEventId={setSelectedEventId}
          />
        );
      case "events":
        return (
          <EventsPage
            events={events}
            onSchedule={scheduleSelectedEvent}
            selectedEvent={selectedEvent}
            setSelectedEventId={setSelectedEventId}
          />
        );
      case "deliveries":
        return (
          <DeliveriesPage
            attempts={attempts}
            deliveries={deliveries}
            executeDelivery={executeSelectedDelivery}
            executeRetryJob={executeRetryJob}
            retryJobs={retryJobs}
            selectedDelivery={selectedDelivery}
            setSelectedDeliveryId={setSelectedDeliveryId}
          />
        );
      case "recovery":
        return (
          <RecoveryPage
            activeReplayForDeadLetter={activeReplayForDeadLetter}
            approveReplayRequest={approveReplayRequest}
            createReplayRequest={createReplayRequest}
            deadLetters={deadLetters}
            executeReplayRequest={executeReplayRequest}
            rejectReplayRequest={rejectReplayRequest}
            replayRequests={replayRequests}
            selectedDeadLetter={selectedDeadLetter}
            setSelectedDeadLetterId={setSelectedDeadLetterId}
          />
        );
      case "overview":
      default:
        return (
          <OverviewPage
            deadLetters={deadLetters}
            destinations={destinations}
            metrics={metrics}
            onNavigate={setActivePage}
            onRefreshDashboard={refreshDashboard}
            onRefreshIntegration={() =>
              selectedSlug
                ? refreshIntegrationScopedData(selectedSlug)
                : Promise.resolve()
            }
            onSelectDeadLetter={setSelectedDeadLetterId}
            onSelectDelivery={setSelectedDeliveryId}
            onSelectEvent={setSelectedEventId}
            recentActivity={recentActivity}
            selectedIntegration={selectedIntegration}
          />
        );
    }
  }
}

function Sidebar({
  activePage,
  onNavigate,
}: {
  activePage: PageKey;
  onNavigate: (page: PageKey) => void;
}) {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 w-64 border-r border-slate-200 bg-white px-4 py-6 shadow-sm lg:w-72 lg:px-5">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
        <p className="text-lg font-bold text-slate-950">RelayGuard</p>
        <p className="mt-1 text-sm text-slate-500">Operator dashboard</p>
      </div>
      <nav aria-label="Dashboard sections" className="mt-6 grid gap-1">
        {NAV_ITEMS.map((item) => {
          const active = activePage === item.key;
          return (
            <button
              className={`rounded-md px-3 py-2 text-left text-sm font-medium transition ${
                active
                  ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"
              }`}
              key={item.key}
              onClick={() => onNavigate(item.key)}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function TopHeader({
  health,
  integrations,
  onRefresh,
  onSelectIntegration,
  selectedSlug,
}: {
  health: HealthState;
  integrations: Integration[];
  onRefresh: () => void;
  onSelectIntegration: (slug: string) => void;
  selectedSlug: string;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
            Local API
          </p>
          <h1 className="text-xl font-semibold text-slate-950">RelayGuard</h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={health === "ok" ? "active" : health} />
          <select
            aria-label="Selected integration"
            className="max-w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            onChange={(event) => onSelectIntegration(event.target.value)}
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
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
            onClick={onRefresh}
            type="button"
          >
            Refresh
          </button>
        </div>
      </div>
    </header>
  );
}

function PageHeader({
  activePage,
  selectedIntegration,
}: {
  activePage: PageKey;
  selectedIntegration: Integration | undefined;
}) {
  const title =
    NAV_ITEMS.find((item) => item.key === activePage)?.label ?? "Overview";
  return (
    <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">
          {selectedIntegration
            ? `${selectedIntegration.name} · ${selectedIntegration.slug}`
            : "Select or seed an integration to begin."}
        </p>
      </div>
    </div>
  );
}

function OverviewPage({
  deadLetters,
  destinations,
  metrics,
  onNavigate,
  onRefreshDashboard,
  onRefreshIntegration,
  onSelectDeadLetter,
  onSelectDelivery,
  onSelectEvent,
  recentActivity,
  selectedIntegration,
}: {
  deadLetters: DeadLetter[];
  destinations: Destination[];
  metrics: {
    events: number;
    scheduled: number;
    delivered: number;
    openDeadLetters: number;
    pendingReplays: number;
  };
  onNavigate: (page: PageKey) => void;
  onRefreshDashboard: () => Promise<void>;
  onRefreshIntegration: () => Promise<void>;
  onSelectDeadLetter: (deadLetterId: string) => void;
  onSelectDelivery: (deliveryId: string) => void;
  onSelectEvent: (eventId: string) => void;
  recentActivity: Array<{
    id: string;
    label: string;
    meta: string;
    status: string;
  }>;
  selectedIntegration: Integration | undefined;
}) {
  return (
    <div className="grid gap-5">
      <GuidedDemo
        destinations={destinations}
        onNavigate={onNavigate}
        onRefreshDashboard={onRefreshDashboard}
        onRefreshIntegration={onRefreshIntegration}
        onSelectDeadLetter={onSelectDeadLetter}
        onSelectDelivery={onSelectDelivery}
        onSelectEvent={onSelectEvent}
        selectedIntegration={selectedIntegration}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Recent events"
          value={metrics.events}
          helper="Safe metadata rows"
        />
        <MetricCard
          label="Scheduled deliveries"
          value={metrics.scheduled}
          helper="Waiting for execution"
          tone="amber"
        />
        <MetricCard
          label="Delivered deliveries"
          value={metrics.delivered}
          helper="Completed via API"
          tone="emerald"
        />
        <MetricCard
          label="Recovery"
          value={metrics.openDeadLetters}
          helper={`${metrics.pendingReplays} pending replays`}
          tone={deadLetters.length > 0 ? "rose" : "cyan"}
        />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel title="Recent activity">
          {recentActivity.length === 0 ? (
            <EmptyState
              title="No activity yet"
              message="Submit a webhook to start the reliability lifecycle."
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {recentActivity.map((activity) => (
                <div
                  className="flex items-center justify-between gap-4 py-3"
                  key={activity.id}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">
                      {activity.label}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {activity.meta}
                    </p>
                  </div>
                  <StatusBadge status={activity.status} />
                </div>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Quick actions">
          <div className="grid gap-2">
            {[
              [
                "Integrations",
                "Activate a sandbox integration",
                "integrations",
              ],
              ["Route Setup", "Create destination and route", "route-setup"],
              ["Webhook Tester", "Submit a demo webhook", "webhook-tester"],
              ["Events", "Schedule deliveries", "events"],
              ["Recovery", "Inspect dead letters and replay", "recovery"],
            ].map(([label, helper, page]) => (
              <button
                className="rounded-md border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-indigo-200 hover:bg-indigo-50"
                key={label}
                onClick={() => onNavigate(page as PageKey)}
                type="button"
              >
                <p className="text-sm font-semibold text-slate-900">{label}</p>
                <p className="text-xs text-slate-500">{helper}</p>
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function IntegrationsPage({
  integrations,
  onSelect,
  onSetStatus,
  selectedIntegration,
}: {
  integrations: Integration[];
  onSelect: (slug: string) => void;
  onSetStatus: (status: "active" | "disabled") => void;
  selectedIntegration: Integration | undefined;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
      <Panel title="Integration list">
        {integrations.length === 0 ? (
          <EmptyState
            title="No integrations"
            message="Run the seed command to create sandbox integrations."
          />
        ) : (
          <DataTable
            columns={["Name", "Slug", "Status", "Updated"]}
            rows={integrations.map((integration) => ({
              id: integration.integration_id,
              cells: [
                integration.name,
                integration.slug,
                <StatusBadge key="status" status={integration.status} />,
                formatDate(integration.updated_at),
              ],
              onClick: () => onSelect(integration.slug),
            }))}
          />
        )}
      </Panel>
      <Panel title="Selected integration">
        {selectedIntegration ? (
          <div className="space-y-4">
            <KeyValue label="Slug" value={selectedIntegration.slug} />
            <KeyValue
              label="Integration ID"
              value={selectedIntegration.integration_id}
            />
            <StatusBadge status={selectedIntegration.status} />
            <div className="flex flex-wrap gap-2">
              <PrimaryButton onClick={() => onSetStatus("active")}>
                Activate
              </PrimaryButton>
              <SecondaryButton onClick={() => onSetStatus("disabled")}>
                Disable
              </SecondaryButton>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No selection"
            message="Select an integration from the table."
          />
        )}
      </Panel>
    </div>
  );
}

function RouteSetupPage({
  createDestination,
  createRoutingRule,
  destinationDraft,
  destinations,
  routingRules,
  ruleDraft,
  selectedSlug,
  setDestinationDraft,
  setRuleDraft,
  updateDestinationStatus,
  updateRoutingRuleStatus,
}: {
  createDestination: (event: FormEvent<HTMLFormElement>) => void;
  createRoutingRule: (event: FormEvent<HTMLFormElement>) => void;
  destinationDraft: {
    name: string;
    endpoint_url: string;
    timeout_seconds: number;
    max_attempts: number;
  };
  destinations: Destination[];
  routingRules: RoutingRule[];
  ruleDraft: {
    name: string;
    destination_id: string;
    event_type: string;
    priority: number;
  };
  selectedSlug: string;
  setDestinationDraft: Dispatch<SetStateAction<typeof destinationDraft>>;
  setRuleDraft: Dispatch<SetStateAction<typeof ruleDraft>>;
  updateDestinationStatus: (
    destinationId: string,
    status: "active" | "disabled",
  ) => void;
  updateRoutingRuleStatus: (
    routingRuleId: string,
    status: "active" | "disabled",
  ) => void;
}) {
  const destinationNameById = new Map(
    destinations.map((destination) => [
      destination.destination_id,
      `${destination.name} - ${destination.endpoint_url}`,
    ]),
  );

  return (
    <div className="grid gap-5">
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Create destination">
          <form className="grid gap-3" onSubmit={createDestination}>
            <TextInput
              label="Name"
              onChange={(value) =>
                setDestinationDraft((current) => ({ ...current, name: value }))
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
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-sm font-semibold text-slate-900">
                Local demo receiver URLs
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Start `python demo/receiver.py`, then quick-fill a destination
                to demonstrate delivery success, retry, rejection, or timeout.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {DEMO_RECEIVER_URLS.map((target) => (
                  <button
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-indigo-200 hover:bg-indigo-50"
                    key={target.url}
                    onClick={() =>
                      setDestinationDraft((current) => ({
                        ...current,
                        endpoint_url: target.url,
                      }))
                    }
                    type="button"
                  >
                    <span className="block text-sm font-semibold text-slate-900">
                      {target.label}
                    </span>
                    <span className="block font-mono text-xs text-slate-600">
                      {target.url}
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">
                      {target.helper}
                    </span>
                  </button>
                ))}
              </div>
            </div>
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
          <form className="grid gap-3" onSubmit={createRoutingRule}>
            <TextInput
              label="Name"
              onChange={(value) =>
                setRuleDraft((current) => ({ ...current, name: value }))
              }
              value={ruleDraft.name}
            />
            <label className="grid gap-1 text-sm">
              <span className="font-medium text-slate-700">Destination</span>
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
                disabled={destinations.length === 0}
                onChange={(event) =>
                  setRuleDraft((current) => ({
                    ...current,
                    destination_id: event.target.value,
                  }))
                }
                required
                value={ruleDraft.destination_id}
              >
                {destinations.length === 0 ? (
                  <option value="">No destinations available</option>
                ) : null}
                {destinations.map((destination) => (
                  <option
                    key={destination.destination_id}
                    value={destination.destination_id}
                  >
                    {destination.name} - {destination.endpoint_url}
                  </option>
                ))}
              </select>
            </label>
            {destinations.length === 0 ? (
              <EmptyState
                title="Create a destination before adding a routing rule."
                message="Routing rules need an explicit downstream target."
              />
            ) : null}
            <TextInput
              label="Event type"
              onChange={(value) =>
                setRuleDraft((current) => ({ ...current, event_type: value }))
              }
              value={ruleDraft.event_type}
            />
            <NumberInput
              label="Priority"
              onChange={(value) =>
                setRuleDraft((current) => ({ ...current, priority: value }))
              }
              value={ruleDraft.priority}
            />
            <PrimaryButton
              disabled={!selectedSlug || ruleDraft.destination_id === ""}
            >
              Create routing rule
            </PrimaryButton>
          </form>
        </Panel>
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <ResourceList
          empty="Create a destination to receive scheduled deliveries."
          items={destinations.map((destination) => ({
            actions: (
              <div className="mt-3 flex gap-2">
                <SecondaryButton
                  disabled={destination.status === "active"}
                  onClick={() =>
                    updateDestinationStatus(
                      destination.destination_id,
                      "active",
                    )
                  }
                >
                  Activate
                </SecondaryButton>
                <SecondaryButton
                  disabled={destination.status === "disabled"}
                  onClick={() =>
                    updateDestinationStatus(
                      destination.destination_id,
                      "disabled",
                    )
                  }
                >
                  Disable
                </SecondaryButton>
              </div>
            ),
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
            actions: (
              <div className="mt-3 flex gap-2">
                <SecondaryButton
                  disabled={rule.status === "active"}
                  onClick={() =>
                    updateRoutingRuleStatus(rule.routing_rule_id, "active")
                  }
                >
                  Activate
                </SecondaryButton>
                <SecondaryButton
                  disabled={rule.status === "disabled"}
                  onClick={() =>
                    updateRoutingRuleStatus(rule.routing_rule_id, "disabled")
                  }
                >
                  Disable
                </SecondaryButton>
              </div>
            ),
            id: rule.routing_rule_id,
            title: rule.name,
            subtitle: `${rule.event_type} -> ${
              destinationNameById.get(rule.destination_id) ??
              shortId(rule.destination_id)
            }`,
            status: rule.status,
          }))}
          title="Routing rules"
        />
      </div>
    </div>
  );
}

function WebhookTesterPage({
  onSubmit,
  recentWebhookResults,
  selectedIntegration,
  setActivePage,
  setSelectedEventId,
}: {
  onSubmit: (draft: WebhookDraft) => Promise<void>;
  recentWebhookResults: WebhookResult[];
  selectedIntegration: Integration | undefined;
  setActivePage: (page: PageKey) => void;
  setSelectedEventId: (eventId: string) => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <Panel title="Submit demo event">
        <EventTester
          disabled={
            !selectedIntegration || selectedIntegration.status !== "active"
          }
          onSubmit={onSubmit}
        />
      </Panel>
      <Panel title="Response panel">
        {recentWebhookResults.length === 0 ? (
          <EmptyState
            title="No submissions yet"
            message="Submit a webhook to see accepted or duplicate responses."
          />
        ) : (
          <div className="grid gap-3">
            {recentWebhookResults.map((result) => (
              <button
                className="rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50"
                key={result.receipt_id}
                onClick={() => {
                  setSelectedEventId(result.event_id);
                  setActivePage("events");
                }}
                type="button"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs text-slate-600">
                    {shortId(result.event_id)}
                  </span>
                  <StatusBadge
                    status={result.duplicate ? "duplicate" : result.status}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  receipt {shortId(result.receipt_id)}
                </p>
              </button>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function EventsPage({
  events,
  onSchedule,
  selectedEvent,
  setSelectedEventId,
}: {
  events: EventMetadata[];
  onSchedule: () => void;
  selectedEvent: EventMetadata | undefined;
  setSelectedEventId: (eventId: string) => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
      <Panel title="Recent events">
        {events.length === 0 ? (
          <EmptyState
            title="No events"
            message="Submit a webhook to create a canonical event."
          />
        ) : (
          <DataTable
            columns={["Type", "Event ID", "Status", "Accepted"]}
            rows={events.map((event) => ({
              id: event.event_id,
              cells: [
                event.event_type,
                shortId(event.event_id),
                <StatusBadge key="status" status={event.status} />,
                formatDate(event.accepted_at),
              ],
              onClick: () => setSelectedEventId(event.event_id),
            }))}
          />
        )}
      </Panel>
      <Panel title="Event detail">
        {selectedEvent ? (
          <div className="space-y-4">
            <KeyValue label="Event ID" value={selectedEvent.event_id} />
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
              onClick={onSchedule}
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
  );
}

function DeliveriesPage({
  attempts,
  deliveries,
  executeDelivery,
  executeRetryJob,
  retryJobs,
  selectedDelivery,
  setSelectedDeliveryId,
}: {
  attempts: DeliveryAttempt[];
  deliveries: Delivery[];
  executeDelivery: () => void;
  executeRetryJob: (retryJobId: string) => void;
  retryJobs: RetryJob[];
  selectedDelivery: Delivery | undefined;
  setSelectedDeliveryId: (deliveryId: string) => void;
}) {
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel title="Delivery list">
          {deliveries.length === 0 ? (
            <EmptyState
              title="No deliveries"
              message="Schedule deliveries for an accepted event."
            />
          ) : (
            <DataTable
              columns={[
                "Delivery",
                "Event type",
                "Destination",
                "Status",
                "Attempts",
                "Last attempt",
              ]}
              rows={deliveries.map((delivery) => ({
                id: delivery.delivery_id,
                cells: [
                  shortId(delivery.delivery_id),
                  delivery.event_type ?? shortId(delivery.event_id),
                  delivery.destination_name ?? shortId(delivery.destination_id),
                  <StatusBadge key="status" status={delivery.status} />,
                  String(delivery.attempt_count),
                  delivery.last_attempt_at
                    ? formatDate(delivery.last_attempt_at)
                    : delivery.next_attempt_at
                      ? `due ${formatDate(delivery.next_attempt_at)}`
                      : "none",
                ],
                onClick: () => setSelectedDeliveryId(delivery.delivery_id),
              }))}
            />
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
              {selectedDelivery.destination_name ? (
                <KeyValue
                  label="Destination"
                  value={selectedDelivery.destination_name}
                />
              ) : null}
              <KeyValue
                label="Routing rule ID"
                value={selectedDelivery.routing_rule_id ?? "manual"}
              />
              {selectedDelivery.routing_rule_name ? (
                <KeyValue
                  label="Routing rule"
                  value={selectedDelivery.routing_rule_name}
                />
              ) : null}
              <StatusBadge status={selectedDelivery.status} />
              <PrimaryButton
                disabled={
                  !["scheduled", "failed"].includes(selectedDelivery.status)
                }
                onClick={executeDelivery}
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
      <div className="grid gap-5 xl:grid-cols-2">
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
                  className="rounded-lg border border-slate-200 bg-white p-3"
                  key={attempt.attempt_id}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-slate-900">
                      Attempt {attempt.attempt_number}
                    </span>
                    <StatusBadge status={attempt.outcome} />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
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
                  className="rounded-lg border border-slate-200 bg-white p-3"
                  key={job.retry_job_id}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="font-mono text-xs text-slate-600">
                      {shortId(job.retry_job_id)}
                    </span>
                    <StatusBadge status={job.status} />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    run at {formatDate(job.run_at)}
                  </p>
                  <SecondaryButton
                    disabled={job.status !== "pending"}
                    onClick={() => executeRetryJob(job.retry_job_id)}
                  >
                    Execute retry
                  </SecondaryButton>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function RecoveryPage({
  activeReplayForDeadLetter,
  approveReplayRequest,
  createReplayRequest,
  deadLetters,
  executeReplayRequest,
  rejectReplayRequest,
  replayRequests,
  selectedDeadLetter,
  setSelectedDeadLetterId,
}: {
  activeReplayForDeadLetter: ReplayRequest | undefined;
  approveReplayRequest: () => void;
  createReplayRequest: () => void;
  deadLetters: DeadLetter[];
  executeReplayRequest: () => void;
  rejectReplayRequest: () => void;
  replayRequests: ReplayRequest[];
  selectedDeadLetter: DeadLetter | undefined;
  setSelectedDeadLetterId: (deadLetterId: string) => void;
}) {
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel title="Dead letters">
          {deadLetters.length === 0 ? (
            <EmptyState
              title="No dead letters"
              message="Terminal delivery failures appear here."
            />
          ) : (
            <DataTable
              columns={["Dead letter", "Reason", "Status", "Created"]}
              rows={deadLetters.map((deadLetter) => ({
                id: deadLetter.dead_letter_id,
                cells: [
                  shortId(deadLetter.dead_letter_id),
                  deadLetter.reason_code,
                  <StatusBadge
                    key="status"
                    status={deadLetter.resolution_status}
                  />,
                  formatDate(deadLetter.dead_lettered_at),
                ],
                onClick: () =>
                  setSelectedDeadLetterId(deadLetter.dead_letter_id),
              }))}
            />
          )}
        </Panel>
        <Panel title="Replay actions">
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
              <StatusBadge status={selectedDeadLetter.resolution_status} />
              {activeReplayForDeadLetter ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-sm font-medium text-slate-900">
                    Active replay
                  </p>
                  <p className="mt-1 font-mono text-xs text-slate-500">
                    {shortId(activeReplayForDeadLetter.replay_request_id)}
                  </p>
                  <div className="mt-3">
                    <StatusBadge status={activeReplayForDeadLetter.status} />
                  </div>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <PrimaryButton
                  disabled={
                    selectedDeadLetter.resolution_status === "resolved" ||
                    activeReplayForDeadLetter !== undefined
                  }
                  onClick={createReplayRequest}
                >
                  Create replay
                </PrimaryButton>
                <SecondaryButton
                  disabled={activeReplayForDeadLetter?.status !== "pending"}
                  onClick={approveReplayRequest}
                >
                  Approve
                </SecondaryButton>
                <SecondaryButton
                  disabled={
                    activeReplayForDeadLetter === undefined ||
                    !["pending", "approved"].includes(
                      activeReplayForDeadLetter.status,
                    )
                  }
                  onClick={rejectReplayRequest}
                >
                  Reject
                </SecondaryButton>
                <PrimaryButton
                  disabled={activeReplayForDeadLetter?.status !== "approved"}
                  onClick={executeReplayRequest}
                >
                  Execute replay
                </PrimaryButton>
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
    </div>
  );
}

function Panel({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      {children}
    </div>
  );
}

function ResourceList({
  empty,
  items,
  title,
}: {
  empty: string;
  items: Array<{
    actions?: ReactNode;
    id: string;
    title: string;
    subtitle: string;
    status: string;
  }>;
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
              className="rounded-lg border border-slate-200 bg-white p-3"
              key={item.id}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="font-medium text-slate-900">{item.title}</p>
                <StatusBadge status={item.status} />
              </div>
              <p className="mt-2 text-xs text-slate-500">{item.subtitle}</p>
              {item.actions ? item.actions : null}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<{ id: string; cells: ReactNode[]; onClick?: () => void }>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((column) => (
              <th className="px-3 py-2 font-semibold" key={column}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr
              className="cursor-pointer transition hover:bg-indigo-50/60"
              key={row.id}
              onClick={row.onClick}
            >
              {row.cells.map((cell, index) => (
                <td
                  className="px-3 py-3 text-slate-700"
                  key={`${row.id}-${index}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
      <span className="font-medium text-slate-700">{label}</span>
      <input
        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
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
      <span className="font-medium text-slate-700">{label}</span>
      <input
        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
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
      className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
      disabled={disabled}
      onClick={onClick ? () => onClick() : undefined}
      type={onClick ? "button" : "submit"}
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="mt-3 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-1 break-all font-mono text-sm text-slate-800">{value}</p>
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
    error: "border-rose-200 bg-rose-50 text-rose-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
  }[toast.tone];
  return (
    <div
      className={`mb-4 flex items-center justify-between gap-3 rounded-lg border p-3 text-sm ${tone}`}
    >
      <p>{toast.message}</p>
      <button className="font-semibold" onClick={onDismiss} type="button">
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

function mergeDeliveries(incoming: Delivery[], existing: Delivery[]) {
  const merged = new Map<string, Delivery>();
  for (const delivery of incoming) {
    merged.set(delivery.delivery_id, delivery);
  }
  for (const delivery of existing) {
    if (!merged.has(delivery.delivery_id)) {
      merged.set(delivery.delivery_id, delivery);
    }
  }
  return Array.from(merged.values());
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
