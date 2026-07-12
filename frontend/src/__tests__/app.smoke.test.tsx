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
  if (url.includes("/events")) {
    return [];
  }
  if (url.includes("/dead-letters")) {
    return [];
  }
  if (url.includes("/replay-requests")) {
    return [];
  }
  return {};
}
