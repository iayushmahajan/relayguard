export type HealthResponse = {
  status: "ok";
};

export type Integration = {
  integration_id: string;
  slug: string;
  name: string;
  status: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type Destination = {
  destination_id: string;
  integration_id: string;
  name: string;
  destination_type: string;
  endpoint_url: string;
  configuration: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
};

export type RoutingRule = {
  routing_rule_id: string;
  integration_id: string;
  destination_id: string;
  name: string;
  event_type: string;
  priority: number;
  status: string;
  created_at: string;
  updated_at: string;
};

export type WebhookResult = {
  receipt_id: string;
  event_id: string;
  status: string;
  duplicate: boolean;
};

export type EventMetadata = {
  event_id: string;
  integration_id: string;
  event_type: string;
  source_event_id: string | null;
  status: string;
  received_at: string;
  accepted_at: string;
};

export type Delivery = {
  delivery_id: string;
  event_id: string;
  destination_id: string;
  routing_rule_id: string | null;
  status: string;
  next_attempt_at: string | null;
  attempt_count: number;
  created_at: string;
  updated_at: string;
};

export type DeliveryScheduleResult = {
  event_id: string;
  status: string;
  scheduled_count: number;
  already_scheduled_count: number;
};

export type DeliveryExecutionResult = {
  delivery_id: string;
  status: string;
  attempt_number: number;
  retry_scheduled: boolean;
  dead_lettered: boolean;
  next_attempt_at: string | null;
};

export type DeliveryAttempt = {
  attempt_id: string;
  delivery_id: string;
  attempt_number: number;
  outcome: string;
  response_status_code: number | null;
  error_code: string | null;
  error_message: string | null;
  is_retryable: boolean;
  started_at: string;
  finished_at: string | null;
  created_at: string;
};

export type RetryJob = {
  retry_job_id: string;
  delivery_id: string;
  status: string;
  run_at: string;
  claimed_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RetryExecutionResult = {
  retry_job_id: string;
  delivery_id: string;
  retry_status: string;
  delivery_status: string;
};

export type DeadLetter = {
  dead_letter_id: string;
  delivery_id: string;
  severity: string;
  reason_code: string;
  reason_message: string;
  resolution_status: string;
  dead_lettered_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReplayRequest = {
  replay_request_id: string;
  status: string;
  event_id: string;
  delivery_id: string;
  dead_letter_id: string;
  reason: string | null;
  requested_by: string | null;
  approved_by: string | null;
  rejected_by: string | null;
  created_at: string;
  updated_at: string;
  executed_at: string | null;
  resolved_at: string | null;
};

export type ReplayExecutionResult = {
  replay_request_id: string;
  delivery_id: string;
  replay_status: string;
  delivery_status: string;
  attempt_recorded: boolean;
  dead_letter_resolved: boolean;
};

export type DestinationDraft = {
  name: string;
  destination_type: string;
  endpoint_url: string;
  timeout_seconds: number;
  max_attempts: number;
  status: "active" | "disabled";
};

export type DestinationUpdateDraft = {
  name?: string;
  endpoint_url?: string;
  configuration?: Record<string, unknown>;
  status?: "active" | "disabled";
};

export type RoutingRuleDraft = {
  name: string;
  destination_id: string;
  event_type: string;
  priority: number;
  status: "active" | "disabled";
};

export type RoutingRuleUpdateDraft = {
  name?: string;
  destination_id?: string;
  event_type?: string;
  priority?: number;
  status?: "active" | "disabled";
};

export type WebhookDraft = {
  event_type: string;
  deduplication_key: string;
  source_event_id: string;
  payload: Record<string, unknown>;
};
