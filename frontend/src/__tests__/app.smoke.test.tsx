import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { EventTester } from "../components/EventTester";
import { StatusBadge } from "../components/StatusBadge";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RelayGuard dashboard", () => {
  it("renders the operator dashboard shell with mocked backend data", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /^RelayGuard$/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("stripe-sandbox").length).toBeGreaterThan(0);
    expect(screen.getByText(/Quick actions/i)).toBeInTheDocument();
  });

  it("renders fixed sidebar navigation", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    expect(navigation.closest("aside")).toHaveClass("fixed");
    expect(
      within(navigation).getByRole("button", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "Recovery" }),
    ).toBeInTheDocument();
  });

  it("changes visible page content when sidebar items are clicked", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Route Setup" }),
    );

    expect(
      screen.getByRole("heading", { name: "Route Setup" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Create destination").length).toBeGreaterThan(0);
    expect(screen.queryByText("Quick actions")).not.toBeInTheDocument();
  });

  it("shows local demo receiver URLs and quick-fills destinations", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Route Setup" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Retryable fail/i }),
    );

    expect(
      screen.getByText("http://127.0.0.1:9000/success"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("http://127.0.0.1:9000/reject"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Endpoint URL/i)).toHaveValue(
      "http://127.0.0.1:9000/fail",
    );
  });

  it("renders guided demo scenarios", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    expect(await screen.findByText("Guided Mode")).toBeInTheDocument();
    expect(
      screen.getByText(/RelayGuard receives webhook events/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Successful Delivery/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Temporary Failure \+ Retry/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Permanent Failure \+ Recovery/i }),
    ).toBeInTheDocument();
  });

  it("runs the successful guided scenario through real API calls", async () => {
    const fetchMock = vi.fn(createGuidedDemoFetch({ existingSetup: false }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: /Successful Delivery/i }),
    );

    expect(
      await screen.findByText(/Webhook received -> event created/i),
    ).toBeInTheDocument();
    expectSubsequence(getFetchOperations(fetchMock), [
      "POST /api/v1/integrations/stripe-sandbox/destinations",
      "POST /api/v1/integrations/stripe-sandbox/routing-rules",
      "POST /api/v1/integrations/stripe-sandbox/webhooks",
      "POST /api/v1/events/event-success/schedule-deliveries",
      "POST /api/v1/deliveries/delivery-success/execute",
    ]);
  });

  it("reuses existing guided demo setup without duplicate destination or rule creation", async () => {
    const fetchMock = vi.fn(createGuidedDemoFetch({ existingSetup: true }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: /Successful Delivery/i }),
    );

    expect(await screen.findByText(/attempt succeeded/i)).toBeInTheDocument();
    const operations = getFetchOperations(fetchMock);
    expect(operations).not.toContain(
      "POST /api/v1/integrations/stripe-sandbox/destinations",
    );
    expect(operations).not.toContain(
      "POST /api/v1/integrations/stripe-sandbox/routing-rules",
    );
    expect(operations).toContain(
      "POST /api/v1/integrations/stripe-sandbox/webhooks",
    );
  });

  it("shows recovery replay steps in the guided recovery scenario", async () => {
    const fetchMock = vi.fn(createGuidedDemoFetch({ existingSetup: true }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", {
        name: /Permanent Failure \+ Recovery/i,
      }),
    );

    expect(
      await screen.findByText(/Create and approve replay/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Replay requested -> approved/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/delivery rejected -> dead letter created/i),
    ).toBeInTheDocument();
    expect(getFetchOperations(fetchMock)).toContain(
      "POST /api/v1/replay-requests/replay-recovery/execute",
    );
  });

  it("shows retry-job steps in the guided retry scenario", async () => {
    const fetchMock = vi.fn(createGuidedDemoFetch({ existingSetup: true }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", {
        name: /Temporary Failure \+ Retry/i,
      }),
    );

    expect(
      await screen.findByText(/delivery failed with 503/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/retry job is pending/i),
    ).toBeInTheDocument();
    expect(getFetchOperations(fetchMock)).toContain(
      "POST /api/v1/deliveries/delivery-retry/execute",
    );
  });

  it("loads recent deliveries when the Deliveries page opens", async () => {
    const fetchMock = vi.fn(mockDashboardFetch);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Deliveries" }),
    );

    expect(getFetchOperations(fetchMock)).toContain("GET /api/v1/deliveries");
    expect(screen.getByText("No deliveries")).toBeInTheDocument();
  });

  it("shows guided-demo deliveries from recent delivery metadata", async () => {
    const fetchMock = vi.fn(createGuidedDemoFetch({ existingSetup: true }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: /Successful Delivery/i }),
    );
    expect(await screen.findByText(/attempt succeeded/i)).toBeInTheDocument();

    const navigation = screen.getByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Deliveries" }),
    );

    expect(await screen.findByText("demo.success")).toBeInTheDocument();
    expect(screen.getAllByText("Success Receiver").length).toBeGreaterThan(0);
    expect(screen.getAllByText("delivered").length).toBeGreaterThan(0);
  });

  it("explains a failed delivery from the AI helper", async () => {
    const fetchMock = vi.fn(mockAiDashboardFetch);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Deliveries" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Explain failure" }),
    );

    expect(
      await screen.findByText("Temporary downstream outage."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Last attempt returned HTTP 503."),
    ).toBeInTheDocument();
    expect(getFetchOperations(fetchMock)).toContain(
      "POST /api/v1/ai/explain-delivery",
    );
  });

  it("drafts replay text without creating a replay request", async () => {
    const fetchMock = vi.fn(mockAiDashboardFetch);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Recovery" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Draft replay note" }),
    );

    expect(await screen.findByText("Replay after repair.")).toBeInTheDocument();
    expect(
      screen.getByText("Approved after endpoint check."),
    ).toBeInTheDocument();
    expect(getFetchOperations(fetchMock)).not.toContain(
      "POST /api/v1/dead-letters/dead-letter-ai/replay-requests",
    );
  });

  it("inserts generated sample payloads without submitting a webhook", async () => {
    const fetchMock = vi.fn(mockDashboardFetch);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Webhook Tester" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Generate sample payload" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Insert into tester" }),
    );

    expect(screen.getByLabelText(/^Event type$/i)).toHaveValue("invoice.paid");
    expect(screen.getByLabelText(/Deduplication key/i)).toHaveValue(
      "sample-invoice-paid",
    );
    expect(
      (screen.getByLabelText(/Payload JSON/i) as HTMLTextAreaElement).value,
    ).toContain('"currency": "EUR"');
    expect(getFetchOperations(fetchMock)).not.toContain(
      "POST /api/v1/integrations/stripe-sandbox/webhooks",
    );
  });

  it("shows AI helper errors without crashing", async () => {
    const fetchMock = vi.fn(mockAiErrorFetch);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Webhook Tester" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Generate sample payload" }),
    );

    expect(
      await screen.findByText("AI helper unavailable"),
    ).toBeInTheDocument();
  });

  it("blocks routing rule creation until a destination exists", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Route Setup" }),
    );

    expect(screen.getByLabelText(/^Destination$/i)).toBeDisabled();
    expect(
      screen.getByText("Create a destination before adding a routing rule."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create routing rule" }),
    ).toBeDisabled();
  });

  it("sends the selected destination when creating a routing rule", async () => {
    const fetchMock = vi.fn(mockDashboardFetchWithDestinations);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: /Dashboard sections/i,
    });
    await userEvent.click(
      within(navigation).getByRole("button", { name: "Route Setup" }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText(/^Destination$/i)).toHaveValue(
        "22222222-2222-4222-8222-222222222222",
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText(/^Destination$/i),
      "33333333-3333-4333-8333-333333333333",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Create routing rule" }),
    );

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(([input, init]) => {
        const url = typeof input === "string" ? input : input.toString();
        return url.includes("/routing-rules") && init?.method === "POST";
      });
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toEqual(
        expect.objectContaining({
          destination_id: "33333333-3333-4333-8333-333333333333",
        }),
      );
    });
  });

  it("keeps overview compact instead of rendering every workflow section", async () => {
    vi.stubGlobal("fetch", vi.fn(mockDashboardFetch));

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
    expect(screen.queryByText("Payload JSON")).not.toBeInTheDocument();
    expect(screen.queryByText("Delivery list")).not.toBeInTheDocument();
  });

  it("shows a backend unavailable state without crashing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection refused")),
    );

    render(<App />);

    expect(
      await screen.findByText(/Dashboard needs the backend/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders readable lifecycle status text", () => {
    render(<StatusBadge status="dead_lettered" />);

    expect(screen.getByText("dead lettered")).toBeInTheDocument();
  });
});

describe("EventTester", () => {
  it("starts with local demo sample values", () => {
    render(<EventTester disabled={false} onSubmit={vi.fn()} />);

    expect(screen.getByLabelText(/Event type/i)).toHaveValue("invoice.paid");
    expect(screen.getByLabelText(/Deduplication key/i)).toHaveValue(
      "demo-invoice-001",
    );
    expect(screen.getByLabelText(/Source event ID/i)).toHaveValue(
      "stripe_evt_001",
    );
    const payloadValue = (
      screen.getByLabelText(/Payload JSON/i) as HTMLTextAreaElement
    ).value;
    expect(payloadValue).toContain('"customer_id": "cus_demo_001"');
  });

  it("validates JSON object payloads before submitting", async () => {
    const submit = vi.fn();
    render(<EventTester disabled={false} onSubmit={submit} />);

    const textarea = screen.getByLabelText(/Payload JSON/i);
    fireEvent.change(textarea, { target: { value: "[]" } });
    await userEvent.click(
      screen.getByRole("button", { name: /Submit webhook/i }),
    );

    expect(
      await screen.findByText(/Payload must be a JSON object/i),
    ).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("submits parsed webhook draft data", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<EventTester disabled={false} onSubmit={submit} />);

    await userEvent.clear(screen.getByLabelText(/Deduplication key/i));
    await userEvent.type(
      screen.getByLabelText(/Deduplication key/i),
      "stable-key",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Submit webhook/i }),
    );

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        deduplication_key: "stable-key",
        event_type: "invoice.paid",
        payload: expect.objectContaining({ invoice_id: "inv_demo_001" }),
      }),
    );
  });
});

function mockDashboardFetch(input: RequestInfo | URL) {
  const url = typeof input === "string" ? input : input.toString();
  const body = responseFor(url);
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }),
  );
}

function responseFor(url: string) {
  if (url.endsWith("/health")) {
    return { status: "ok" };
  }
  if (url.endsWith("/integrations")) {
    return [
      {
        integration_id: "11111111-1111-4111-8111-111111111111",
        slug: "stripe-sandbox",
        name: "Stripe Sandbox",
        status: "active",
        enabled: true,
        created_at: "2026-07-10T00:00:00Z",
        updated_at: "2026-07-10T00:00:00Z",
      },
    ];
  }
  if (url.includes("/destinations")) {
    return [];
  }
  if (url.includes("/routing-rules")) {
    return [];
  }
  if (url.includes("/deliveries?limit=50")) {
    return [];
  }
  if (url.includes("/events")) {
    return [];
  }
  if (url.includes("/dead-letters")) {
    return [];
  }
  if (url.includes("/replay-requests")) {
    return [];
  }
  if (url.includes("/ai/sample-webhook-payload")) {
    return {
      mode: "fallback",
      event_type: "invoice.paid",
      deduplication_key: "sample-invoice-paid",
      source_event_id: "sample_evt_001",
      payload: {
        invoice_id: "inv_sample_001",
        customer_id: "cus_sample_001",
        amount: 4999,
        currency: "EUR",
      },
    };
  }
  return {};
}

function mockAiDashboardFetch(input: RequestInfo | URL, init?: RequestInit) {
  const url = typeof input === "string" ? input : input.toString();
  if (url.includes("/ai/explain-delivery") && init?.method === "POST") {
    return jsonResponse({
      mode: "fallback",
      summary: "The downstream service returned a retryable error.",
      likely_cause: "Temporary downstream outage.",
      recommended_action: "Retry after checking downstream health.",
      risk_level: "medium",
      supporting_facts: [
        "Delivery status is failed.",
        "Last attempt returned HTTP 503.",
      ],
    });
  }
  if (url.includes("/ai/draft-replay-note") && init?.method === "POST") {
    return jsonResponse({
      mode: "fallback",
      reason: "Replay after repair.",
      approval_note: "Approved after endpoint check.",
      operator_summary: "Dead letter is open with severity high.",
      warnings: ["Confirm the downstream destination is fixed."],
    });
  }
  if (url.includes("/deliveries?limit=50")) {
    return jsonResponse([
      {
        delivery_id: "delivery-ai",
        event_id: "event-ai",
        event_type: "invoice.paid",
        destination_id: "destination-ai",
        destination_name: "Retry Receiver",
        routing_rule_id: "rule-ai",
        routing_rule_name: "Retry route",
        status: "failed",
        attempt_count: 1,
        next_attempt_at: "2026-07-12T00:01:00Z",
        last_attempt_at: "2026-07-12T00:00:00Z",
        created_at: "2026-07-12T00:00:00Z",
        updated_at: "2026-07-12T00:00:00Z",
      },
    ]);
  }
  if (url.includes("/attempts")) {
    return jsonResponse([
      {
        attempt_id: "attempt-ai",
        delivery_id: "delivery-ai",
        attempt_number: 1,
        outcome: "failed",
        response_status_code: 503,
        error_code: "http_503",
        error_message: "HTTP 503",
        is_retryable: true,
        started_at: "2026-07-12T00:00:00Z",
        finished_at: "2026-07-12T00:00:00Z",
        created_at: "2026-07-12T00:00:00Z",
      },
    ]);
  }
  if (url.includes("/retry-jobs")) {
    return jsonResponse([]);
  }
  if (url.endsWith("/dead-letters")) {
    return jsonResponse([
      {
        dead_letter_id: "dead-letter-ai",
        delivery_id: "delivery-ai",
        severity: "high",
        reason_code: "http_404",
        reason_message: "Rejected",
        resolution_status: "open",
        dead_lettered_at: "2026-07-12T00:00:00Z",
        resolved_at: null,
        created_at: "2026-07-12T00:00:00Z",
        updated_at: "2026-07-12T00:00:00Z",
      },
    ]);
  }
  return mockDashboardFetch(input);
}

function mockAiErrorFetch(input: RequestInfo | URL, init?: RequestInit) {
  const url = typeof input === "string" ? input : input.toString();
  if (url.includes("/ai/sample-webhook-payload") && init?.method === "POST") {
    return Promise.resolve(
      new Response(JSON.stringify({ detail: "AI helper unavailable" }), {
        headers: { "Content-Type": "application/json" },
        status: 503,
      }),
    );
  }
  return mockDashboardFetch(input);
}

function mockDashboardFetchWithDestinations(
  input: RequestInfo | URL,
  init?: RequestInit,
) {
  const url = typeof input === "string" ? input : input.toString();
  if (url.includes("/routing-rules") && init?.method === "POST") {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          routing_rule_id: "44444444-4444-4444-8444-444444444444",
          integration_id: "11111111-1111-4111-8111-111111111111",
          destination_id: JSON.parse(String(init.body)).destination_id,
          name: "Invoice paid to billing",
          event_type: "invoice.paid",
          priority: 100,
          status: "active",
          created_at: "2026-07-10T00:00:00Z",
          updated_at: "2026-07-10T00:00:00Z",
        }),
        {
          headers: { "Content-Type": "application/json" },
          status: 201,
        },
      ),
    );
  }
  const body = responseFor(url);
  return Promise.resolve(
    new Response(
      JSON.stringify(
        url.includes("/destinations")
          ? [
              {
                destination_id: "22222222-2222-4222-8222-222222222222",
                integration_id: "11111111-1111-4111-8111-111111111111",
                name: "Success Receiver",
                destination_type: "http",
                endpoint_url: "http://127.0.0.1:9000/success",
                configuration: {},
                status: "active",
                created_at: "2026-07-10T00:00:00Z",
                updated_at: "2026-07-10T00:00:00Z",
              },
              {
                destination_id: "33333333-3333-4333-8333-333333333333",
                integration_id: "11111111-1111-4111-8111-111111111111",
                name: "Reject Receiver",
                destination_type: "http",
                endpoint_url: "http://127.0.0.1:9000/reject",
                configuration: {},
                status: "active",
                created_at: "2026-07-10T00:00:00Z",
                updated_at: "2026-07-10T00:00:00Z",
              },
            ]
          : body,
      ),
      {
        headers: { "Content-Type": "application/json" },
        status: 200,
      },
    ),
  );
}

function createGuidedDemoFetch({ existingSetup }: { existingSetup: boolean }) {
  const destinations = existingSetup
    ? [
        destinationFixture(
          "destination-success",
          "Success Receiver",
          "http://127.0.0.1:9000/success",
        ),
        destinationFixture(
          "destination-recovery",
          "Reject Receiver",
          "http://127.0.0.1:9000/reject",
        ),
        destinationFixture(
          "destination-retry",
          "Retry Receiver",
          "http://127.0.0.1:9000/fail",
        ),
      ]
    : [];
  const routingRules = existingSetup
    ? [
        routingRuleFixture(
          "rule-success",
          "Demo Success Route",
          "demo.success",
          "destination-success",
        ),
        routingRuleFixture(
          "rule-recovery",
          "Demo Recovery Route",
          "demo.recovery",
          "destination-recovery",
        ),
        routingRuleFixture(
          "rule-retry",
          "Demo Retry Route",
          "demo.retry",
          "destination-retry",
        ),
      ]
    : [];
  const deliveries: Record<string, unknown[]> = {
    "event-success": [
      deliveryFixture(
        "delivery-success",
        "event-success",
        "destination-success",
        "rule-success",
      ),
    ],
    "event-recovery": [
      deliveryFixture(
        "delivery-recovery",
        "event-recovery",
        "destination-recovery",
        "rule-recovery",
      ),
    ],
    "event-retry": [
      deliveryFixture(
        "delivery-retry",
        "event-retry",
        "destination-retry",
        "rule-retry",
      ),
    ],
  };
  const deadLetters: unknown[] = [];
  const replayRequests: unknown[] = [];

  return (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/health")) {
      return jsonResponse({ status: "ok" });
    }
    if (url.endsWith("/integrations")) {
      return jsonResponse([integrationFixture()]);
    }
    if (url.endsWith("/destinations") && method === "GET") {
      return jsonResponse(destinations);
    }
    if (url.endsWith("/destinations") && method === "POST") {
      const body = JSON.parse(String(init?.body));
      const destinationId =
        body.name === "Success Receiver"
          ? "destination-success"
          : body.name === "Retry Receiver"
            ? "destination-retry"
            : "destination-recovery";
      const destination = destinationFixture(
        destinationId,
        body.name,
        body.endpoint_url,
      );
      destinations.push(destination);
      return jsonResponse(destination, 201);
    }
    if (url.includes("/destinations/") && method === "PATCH") {
      const destinationId = url.split("/").at(-1);
      const body = JSON.parse(String(init?.body));
      const destination = destinations.find(
        (candidate) => candidate.destination_id === destinationId,
      );
      Object.assign(destination ?? {}, {
        endpoint_url: body.endpoint_url ?? destination?.endpoint_url,
        status: body.status ?? destination?.status,
      });
      return jsonResponse(destination);
    }
    if (url.endsWith("/routing-rules") && method === "GET") {
      return jsonResponse(routingRules);
    }
    if (url.endsWith("/routing-rules") && method === "POST") {
      const body = JSON.parse(String(init?.body));
      const routingRuleId =
        body.event_type === "demo.success"
          ? "rule-success"
          : body.event_type === "demo.retry"
            ? "rule-retry"
            : "rule-recovery";
      const rule = routingRuleFixture(
        routingRuleId,
        body.name,
        body.event_type,
        body.destination_id,
      );
      routingRules.push(rule);
      return jsonResponse(rule, 201);
    }
    if (url.includes("/routing-rules/") && method === "PATCH") {
      const routingRuleId = url.split("/").at(-1);
      const body = JSON.parse(String(init?.body));
      const rule = routingRules.find(
        (candidate) => candidate.routing_rule_id === routingRuleId,
      );
      Object.assign(rule ?? {}, {
        destination_id: body.destination_id ?? rule?.destination_id,
        event_type: body.event_type ?? rule?.event_type,
        priority: body.priority ?? rule?.priority,
        status: body.status ?? rule?.status,
      });
      return jsonResponse(rule);
    }
    if (url.includes("/webhooks") && method === "POST") {
      const body = JSON.parse(String(init?.body));
      const key =
        body.event_type === "demo.recovery"
          ? "recovery"
          : body.event_type === "demo.retry"
            ? "retry"
            : "success";
      return jsonResponse(
        {
          receipt_id: `receipt-${key}`,
          event_id: `event-${key}`,
          status: "accepted",
          duplicate: false,
        },
        202,
      );
    }
    if (url.includes("/schedule-deliveries") && method === "POST") {
      const eventId = url.split("/").at(-2) ?? "event-success";
      return jsonResponse({
        event_id: eventId,
        status: "accepted",
        scheduled_count: 1,
        already_scheduled_count: 0,
      });
    }
    if (url.includes("/events/") && url.endsWith("/deliveries")) {
      const eventId = url.split("/").at(-2) ?? "event-success";
      return jsonResponse(deliveries[eventId] ?? []);
    }
    if (url.includes("/deliveries?limit=50")) {
      return jsonResponse(Object.values(deliveries).flat());
    }
    if (url.endsWith("/execute") && url.includes("/deliveries/")) {
      const deliveryId = url.split("/").at(-2);
      if (deliveryId === "delivery-retry") {
        updateDeliveryStatus(deliveries, "delivery-retry", "failed");
        return jsonResponse({
          delivery_id: deliveryId,
          status: "failed",
          attempt_number: 1,
          retry_scheduled: true,
          dead_lettered: false,
          next_attempt_at: "2026-07-12T00:05:00Z",
        });
      }
      if (deliveryId === "delivery-recovery") {
        updateDeliveryStatus(deliveries, "delivery-recovery", "dead_lettered");
        deadLetters.push({
          dead_letter_id: "dead-letter-recovery",
          delivery_id: "delivery-recovery",
          severity: "high",
          reason_code: "http_400",
          reason_message: "Rejected",
          resolution_status: "open",
          dead_lettered_at: "2026-07-12T00:00:00Z",
          resolved_at: null,
          created_at: "2026-07-12T00:00:00Z",
          updated_at: "2026-07-12T00:00:00Z",
        });
        return jsonResponse({
          delivery_id: deliveryId,
          status: "dead_lettered",
          attempt_number: 1,
          retry_scheduled: false,
          dead_lettered: true,
          next_attempt_at: null,
        });
      }
      updateDeliveryStatus(deliveries, "delivery-success", "delivered");
      return jsonResponse({
        delivery_id: deliveryId,
        status: "delivered",
        attempt_number: 1,
        retry_scheduled: false,
        dead_lettered: false,
        next_attempt_at: null,
      });
    }
    if (url.includes("/attempts")) {
      return jsonResponse([
        {
          attempt_id: "attempt-success",
          delivery_id: "delivery-success",
          attempt_number: 1,
          outcome: "succeeded",
          response_status_code: 200,
          error_code: null,
          error_message: null,
          is_retryable: false,
          started_at: "2026-07-12T00:00:00Z",
          finished_at: "2026-07-12T00:00:00Z",
          created_at: "2026-07-12T00:00:00Z",
        },
      ]);
    }
    if (url.includes("/retry-jobs")) {
      if (url.includes("delivery-retry")) {
        return jsonResponse([
          {
            retry_job_id: "retry-job-retry",
            delivery_id: "delivery-retry",
            status: "pending",
            run_at: "2026-07-12T00:05:00Z",
            claimed_at: null,
            completed_at: null,
            created_at: "2026-07-12T00:00:00Z",
            updated_at: "2026-07-12T00:00:00Z",
          },
        ]);
      }
      return jsonResponse([]);
    }
    if (url.endsWith("/dead-letters") && method === "GET") {
      return jsonResponse(deadLetters);
    }
    if (url.includes("/dead-letters/") && url.endsWith("/replay-requests")) {
      const replay = {
        replay_request_id: "replay-recovery",
        status: "pending",
        event_id: "event-recovery",
        delivery_id: "delivery-recovery",
        dead_letter_id: "dead-letter-recovery",
        reason: "Downstream was repaired during the guided demo.",
        requested_by: "guided-demo",
        approved_by: null,
        rejected_by: null,
        created_at: "2026-07-12T00:00:00Z",
        updated_at: "2026-07-12T00:00:00Z",
        executed_at: null,
        resolved_at: null,
      };
      replayRequests.push(replay);
      return jsonResponse(replay, 201);
    }
    if (url.endsWith("/replay-requests") && method === "GET") {
      return jsonResponse(replayRequests);
    }
    if (url.includes("/replay-requests/") && url.endsWith("/approve")) {
      const replay = replayRequests[0] as Record<string, unknown>;
      replay.status = "approved";
      replay.approved_by = "guided-demo";
      return jsonResponse(replay);
    }
    if (url.includes("/replay-requests/") && url.endsWith("/execute")) {
      const replay = replayRequests[0] as Record<string, unknown>;
      replay.status = "resolved";
      const deadLetter = deadLetters[0] as Record<string, unknown>;
      deadLetter.resolution_status = "resolved";
      updateDeliveryStatus(deliveries, "delivery-recovery", "delivered");
      return jsonResponse({
        replay_request_id: "replay-recovery",
        delivery_id: "delivery-recovery",
        replay_status: "resolved",
        delivery_status: "delivered",
        attempt_recorded: true,
        dead_letter_resolved: true,
      });
    }
    if (url.includes("/events")) {
      return jsonResponse([]);
    }
    return jsonResponse({});
  };
}

function getFetchOperations(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.map(([input, init]) => {
    const url = typeof input === "string" ? input : input.toString();
    const parsed = url.startsWith("http") ? new URL(url) : null;
    const path = parsed ? parsed.pathname : url.split("?")[0];
    return `${init?.method ?? "GET"} ${path}`;
  });
}

function expectSubsequence(operations: string[], expected: string[]) {
  let cursor = 0;
  for (const operation of operations) {
    if (operation === expected[cursor]) {
      cursor += 1;
    }
  }
  expect(cursor).toBe(expected.length);
}

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
      status,
    }),
  );
}

function integrationFixture() {
  return {
    integration_id: "11111111-1111-4111-8111-111111111111",
    slug: "stripe-sandbox",
    name: "Stripe Sandbox",
    status: "active",
    enabled: true,
    created_at: "2026-07-10T00:00:00Z",
    updated_at: "2026-07-10T00:00:00Z",
  };
}

function destinationFixture(
  destinationId: string,
  name: string,
  endpointUrl: string,
) {
  return {
    destination_id: destinationId,
    integration_id: "11111111-1111-4111-8111-111111111111",
    name,
    destination_type: "http",
    endpoint_url: endpointUrl,
    configuration: {},
    status: "active",
    created_at: "2026-07-10T00:00:00Z",
    updated_at: "2026-07-10T00:00:00Z",
  };
}

function routingRuleFixture(
  routingRuleId: string,
  name: string,
  eventType: string,
  destinationId: string,
) {
  return {
    routing_rule_id: routingRuleId,
    integration_id: "11111111-1111-4111-8111-111111111111",
    destination_id: destinationId,
    name,
    event_type: eventType,
    priority: 100,
    status: "active",
    created_at: "2026-07-10T00:00:00Z",
    updated_at: "2026-07-10T00:00:00Z",
  };
}

function deliveryFixture(
  deliveryId: string,
  eventId: string,
  destinationId: string,
  routingRuleId: string,
) {
  const isRecovery = deliveryId.includes("recovery");
  const isRetry = deliveryId.includes("retry");
  return {
    delivery_id: deliveryId,
    event_id: eventId,
    event_type: isRecovery
      ? "demo.recovery"
      : isRetry
        ? "demo.retry"
        : "demo.success",
    destination_id: destinationId,
    destination_name: isRecovery
      ? "Reject Receiver"
      : isRetry
        ? "Retry Receiver"
        : "Success Receiver",
    routing_rule_id: routingRuleId,
    routing_rule_name: isRecovery
      ? "Demo Recovery Route"
      : isRetry
        ? "Demo Retry Route"
        : "Demo Success Route",
    status: "scheduled",
    next_attempt_at: "2026-07-12T00:00:00Z",
    last_attempt_at: null,
    attempt_count: 0,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
  };
}

function updateDeliveryStatus(
  deliveries: Record<string, unknown[]>,
  deliveryId: string,
  status: string,
) {
  for (const deliveryList of Object.values(deliveries)) {
    const delivery = deliveryList.find(
      (candidate) =>
        typeof candidate === "object" &&
        candidate !== null &&
        "delivery_id" in candidate &&
        candidate.delivery_id === deliveryId,
    ) as Record<string, unknown> | undefined;
    if (delivery) {
      delivery.status = status;
      delivery.attempt_count = 1;
      delivery.last_attempt_at = "2026-07-12T00:00:00Z";
      delivery.next_attempt_at =
        status === "delivered" ? null : delivery.next_attempt_at;
      return;
    }
  }
}
