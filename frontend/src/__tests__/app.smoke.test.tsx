import { render, screen } from "@testing-library/react";

import App from "../App";

describe("RelayGuard app shell", () => {
  it("renders the foundation heading in the main landmark", () => {
    render(<App />);

    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /relayguard foundation/i }),
    ).toBeInTheDocument();
  });
});
