import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Dashboard from "./Dashboard.jsx";

const record = (status = "PENDING") => ({
  id: "abc-123", status, command: "<img src=x onerror=alert(1)>", cwd: "/tmp/lab", source: "agent",
  assessment: { decision: "REVIEW", category: "WRITE", risk_score: 50, reasons: ["Needs review"] },
  created: 1000, expires: 1300,
});
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("loads and safely renders live requests, then approves the exact identity", async () => {
  let current = "PENDING";
  const fetch = vi.fn(async (url, options) => {
    if (options.method === "POST") { current = "APPROVED"; return response(record(current)); }
    return response({ requests: [record(current)] });
  });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("confirm", () => true);
  const { container } = render(<Dashboard />);
  fireEvent.change(screen.getByLabelText("Admin token"), { target: { value: "test-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  await screen.findByText("<img src=x onerror=alert(1)>");
  expect(container.querySelector("img")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Approve request" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Approve request" })).toBeNull());
  expect(screen.getByText("APPROVED", { selector: ".badge" })).toBeTruthy();
  expect(fetch.mock.calls[1][1].headers.Authorization).toBe("Bearer test-secret");
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    command: "<img src=x onerror=alert(1)>", cwd: "/tmp/lab", source: "agent", decision: "APPROVE",
  });
});

it("refreshes an expired request after a stale decision", async () => {
  let current = "PENDING";
  vi.stubGlobal("fetch", vi.fn(async (url, options) => {
    if (options.method === "POST") { current = "EXPIRED"; return response({}, 409); }
    return response({ requests: [record(current)] });
  }));
  vi.stubGlobal("confirm", () => true);
  render(<Dashboard />);
  fireEvent.change(screen.getByLabelText("Admin token"), { target: { value: "test-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  fireEvent.click(await screen.findByRole("button", { name: "Approve request" }));
  await screen.findByText("EXPIRED", { selector: ".badge" });
  expect(screen.queryByRole("button", { name: "Approve request" })).toBeNull();
  expect(screen.getByRole("status").textContent).toMatch(/Decision not applied/);
});

it("shows authentication errors without retaining displayed request data", async () => {
  let authorized = true;
  vi.stubGlobal("fetch", vi.fn(async () => authorized
    ? response({ requests: [record()] }) : response({}, 401)));
  render(<Dashboard />);
  fireEvent.change(screen.getByLabelText("Admin token"), { target: { value: "test-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  await screen.findByText("<img src=x onerror=alert(1)>");
  authorized = false;
  fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
  await screen.findByText(/Access denied/);
  expect(screen.queryByText("<img src=x onerror=alert(1)>")).toBeNull();
});
