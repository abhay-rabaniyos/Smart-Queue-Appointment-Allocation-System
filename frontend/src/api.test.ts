import { it, expect, vi } from "vitest";
import { api, ApiError } from "./api";

it("reuses an uncertain command key after a network failure", async () => {
  const mock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Network failure"))
    .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
  vi.stubGlobal("fetch", mock);
  await expect(
    api("/tickets", "POST", { name: "Uncertain visitor" }),
  ).rejects.toThrow("Network failure");
  await api("/tickets", "POST", { name: "Uncertain visitor" });
  expect(mock.mock.calls[0][1].headers["Idempotency-Key"]).toBe(
    mock.mock.calls[1][1].headers["Idempotency-Key"],
  );
});
it("sends credentials and caller-provided idempotency key", async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(new Response('{"ok":true}', { status: 200 }));
  vi.stubGlobal("fetch", mock);
  expect(await api("/tickets", "POST", { name: "Test" }, "stable-key")).toEqual(
    { ok: true },
  );
  expect(mock).toHaveBeenCalledWith(
    "/api/tickets",
    expect.objectContaining({
      credentials: "include",
      headers: expect.objectContaining({ "Idempotency-Key": "stable-key" }),
    }),
  );
});
it("turns non-JSON errors into readable errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("bad gateway", { status: 502 })),
  );
  await expect(api("/board")).rejects.toBeInstanceOf(ApiError);
});
