import { act, renderHook } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import useErrors from "./useErrors";
import { api } from "../api";
import { apiMessage, publishError } from "../errors";

it("suppresses continuing duplicates even after dismissal and allows a new incident after recovery", () => {
  const { result } = renderHook(() => useErrors());
  act(() => {
    for (let i = 0; i < 5; i++) result.current.report("smtp", "Email rejected");
  });
  expect(result.current.messages).toEqual(["Email rejected"]);
  act(() => result.current.dismiss("Email rejected"));
  act(() => result.current.report("smtp", "Email rejected"));
  expect(result.current.messages).toEqual([]);
  act(() => result.current.resolve("smtp"));
  act(() => result.current.report("smtp", "Email rejected"));
  expect(result.current.messages).toEqual(["Email rejected"]);
});
it("groups equal failures from different sources but keeps unrelated failures visible", () => {
  const { result } = renderHook(() => useErrors());
  act(() => {
    result.current.report("delivery:one", "Email rejected");
    result.current.report("delivery:two", "Email rejected");
    result.current.report("action", "No customers waiting");
  });
  expect(result.current.messages).toEqual([
    "Email rejected",
    "No customers waiting",
  ]);
  act(() => result.current.dismiss("Email rejected"));
  act(() => result.current.report("delivery:three", "Email rejected"));
  expect(result.current.messages).toEqual(["No customers waiting"]);
});
it("receives API action errors once and clears them after a successful retry", async () => {
  const { result } = renderHook(() => useErrors());
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "No customers waiting" }), {
          status: 409,
        }),
    ),
  );
  await act(async () => {
    for (let i = 0; i < 3; i++)
      await api("/counters/test/call", "POST").catch(() => {});
  });
  expect(result.current.messages).toEqual(["No customers waiting"]);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 200 })),
  );
  await act(async () => {
    await api("/counters/test/call", "POST");
  });
  expect(result.current.messages).toEqual([]);
});
it("handles expected anonymous authentication without an error and explains invalid email validation", async () => {
  const { result } = renderHook(() => useErrors());
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Sign in required" }), {
          status: 401,
        }),
    ),
  );
  await act(async () => {
    await api("/auth/me").catch(() => {});
  });
  expect(result.current.messages).toEqual([]);
  expect(
    apiMessage(422, [
      { loc: ["body", "contact"], msg: "value is not a valid email address" },
    ]),
  ).toMatch(/valid email address/);
  expect(apiMessage(500, "secret-provider-response")).not.toContain(
    "secret-provider-response",
  );
});
it("continual background errors do not return after dismissal until a recovery event", () => {
  const { result } = renderHook(() => useErrors());
  act(() =>
    publishError({ source: "GET:/operations", message: "Connection failed" }),
  );
  act(() => result.current.dismiss("Connection failed"));
  act(() =>
    publishError({ source: "GET:/operations", message: "Connection failed" }),
  );
  expect(result.current.messages).toEqual([]);
  act(() => publishError({ source: "GET:/operations" }));
  act(() =>
    publishError({ source: "GET:/operations", message: "Connection failed" }),
  );
  expect(result.current.messages).toEqual(["Connection failed"]);
});
