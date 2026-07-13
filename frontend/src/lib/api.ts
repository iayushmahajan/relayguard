import type {
  DeliveryExplanation,
  DeadLetter,
  Delivery,
  DeliveryAttempt,
  DeliveryExecutionResult,
  DeliveryScheduleResult,
  Destination,
  DestinationDraft,
  DestinationUpdateDraft,
  EventMetadata,
  HealthResponse,
  Integration,
  ReplayExecutionResult,
  ReplayRequest,
  RetryExecutionResult,
  RetryJob,
  RoutingRule,
  RoutingRuleDraft,
  RoutingRuleUpdateDraft,
  ReplayNoteDraft,
  SampleWebhookPayload,
  WebhookDraft,
  WebhookResult,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers:
      options.body === undefined
        ? undefined
        : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const text = await response.text();
  const data = text === "" ? null : (JSON.parse(text) as unknown);
  if (!response.ok) {
    const detail =
      data !== null &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Request failed with HTTP ${response.status}`;
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  listIntegrations: () => request<Integration[]>("/integrations"),
  updateIntegration: (slug: string, status: "active" | "disabled") =>
    request<Integration>(`/integrations/${slug}`, {
      method: "PATCH",
      body: { status },
    }),
  listDestinations: (slug: string) =>
    request<Destination[]>(`/integrations/${slug}/destinations`),
  createDestination: (slug: string, draft: DestinationDraft) =>
    request<Destination>(`/integrations/${slug}/destinations`, {
      method: "POST",
      body: {
        name: draft.name,
        destination_type: draft.destination_type,
        endpoint_url: draft.endpoint_url,
        configuration: {
          timeout_seconds: draft.timeout_seconds,
          max_attempts: draft.max_attempts,
        },
        status: draft.status,
      },
    }),
  updateDestination: (
    slug: string,
    destinationId: string,
    draft: DestinationUpdateDraft,
  ) =>
    request<Destination>(
      `/integrations/${slug}/destinations/${destinationId}`,
      {
        method: "PATCH",
        body: draft,
      },
    ),
  listRoutingRules: (slug: string) =>
    request<RoutingRule[]>(`/integrations/${slug}/routing-rules`),
  createRoutingRule: (slug: string, draft: RoutingRuleDraft) =>
    request<RoutingRule>(`/integrations/${slug}/routing-rules`, {
      method: "POST",
      body: draft,
    }),
  updateRoutingRule: (
    slug: string,
    routingRuleId: string,
    draft: RoutingRuleUpdateDraft,
  ) =>
    request<RoutingRule>(
      `/integrations/${slug}/routing-rules/${routingRuleId}`,
      {
        method: "PATCH",
        body: draft,
      },
    ),
  submitWebhook: (slug: string, draft: WebhookDraft) =>
    request<WebhookResult>(`/integrations/${slug}/webhooks`, {
      method: "POST",
      body: {
        event_type: draft.event_type,
        deduplication_key: draft.deduplication_key,
        source_event_id:
          draft.source_event_id === "" ? undefined : draft.source_event_id,
        payload: draft.payload,
      },
    }),
  listEvents: (integrationSlug?: string) => {
    const query = integrationSlug
      ? `?limit=50&integration_slug=${encodeURIComponent(integrationSlug)}`
      : "?limit=50";
    return request<EventMetadata[]>(`/events${query}`);
  },
  getEvent: (eventId: string) => request<EventMetadata>(`/events/${eventId}`),
  scheduleDeliveries: (eventId: string) =>
    request<DeliveryScheduleResult>(`/events/${eventId}/schedule-deliveries`, {
      method: "POST",
    }),
  listRecentDeliveries: () => request<Delivery[]>("/deliveries?limit=50"),
  listDeliveries: (eventId: string) =>
    request<Delivery[]>(`/events/${eventId}/deliveries`),
  executeDelivery: (deliveryId: string) =>
    request<DeliveryExecutionResult>(`/deliveries/${deliveryId}/execute`, {
      method: "POST",
    }),
  listDeliveryAttempts: (deliveryId: string) =>
    request<DeliveryAttempt[]>(`/deliveries/${deliveryId}/attempts`),
  listRetryJobs: (deliveryId: string) =>
    request<RetryJob[]>(`/deliveries/${deliveryId}/retry-jobs`),
  executeRetryJob: (retryJobId: string) =>
    request<RetryExecutionResult>(`/retry-jobs/${retryJobId}/execute`, {
      method: "POST",
    }),
  listDeadLetters: () => request<DeadLetter[]>("/dead-letters"),
  listReplayRequests: () => request<ReplayRequest[]>("/replay-requests"),
  createReplayRequest: (
    deadLetterId: string,
    reason: string,
    requestedBy: string,
  ) =>
    request<ReplayRequest>(`/dead-letters/${deadLetterId}/replay-requests`, {
      method: "POST",
      body: { reason, requested_by: requestedBy },
    }),
  approveReplayRequest: (
    replayRequestId: string,
    approvedBy: string,
    note: string,
  ) =>
    request<ReplayRequest>(`/replay-requests/${replayRequestId}/approve`, {
      method: "POST",
      body: { approved_by: approvedBy, note },
    }),
  rejectReplayRequest: (
    replayRequestId: string,
    rejectedBy: string,
    reason: string,
  ) =>
    request<ReplayRequest>(`/replay-requests/${replayRequestId}/reject`, {
      method: "POST",
      body: { rejected_by: rejectedBy, reason },
    }),
  executeReplayRequest: (replayRequestId: string) =>
    request<ReplayExecutionResult>(
      `/replay-requests/${replayRequestId}/execute`,
      {
        method: "POST",
      },
    ),
  explainDelivery: (deliveryId: string) =>
    request<DeliveryExplanation>("/ai/explain-delivery", {
      method: "POST",
      body: { delivery_id: deliveryId },
    }),
  draftReplayNote: (deadLetterId: string) =>
    request<ReplayNoteDraft>("/ai/draft-replay-note", {
      method: "POST",
      body: { dead_letter_id: deadLetterId },
    }),
  sampleWebhookPayload: (
    eventType: string,
    description: string,
    integrationSlug?: string,
  ) =>
    request<SampleWebhookPayload>("/ai/sample-webhook-payload", {
      method: "POST",
      body: {
        event_type: eventType,
        description: description.trim() === "" ? undefined : description,
        integration_slug: integrationSlug,
      },
    }),
};
