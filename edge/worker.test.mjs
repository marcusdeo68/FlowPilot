import assert from "node:assert/strict";
import test from "node:test";
import worker from "./worker.mjs";

const env = {
  FLOWPILOT_BROWSER_ORIGIN: "https://flowpilot.test.workers.dev",
  FLOWPILOT_UPSTREAM_ORIGIN: "https://flowpilot-test.up.railway.app",
  FLOWPILOT_PROXY_SECRET: "0123456789abcdef".repeat(4),
};

test("pins upstream, replaces the credential, and returns login redirects and cookies", async (t) => {
  const mocked = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.href, env.FLOWPILOT_UPSTREAM_ORIGIN + "//another.test/path?state=sample");
    assert.equal(options.method, "POST");
    assert.equal(await new Response(options.body).text(), "sample");
    assert.equal(options.headers.get("x-flowpilot-proxy-secret"), env.FLOWPILOT_PROXY_SECRET);
    assert.equal(options.headers.get("origin"), env.FLOWPILOT_BROWSER_ORIGIN);
    assert.equal(options.headers.get("cookie"), "example=value");
    assert.equal(options.headers.has("forwarded"), false);
    assert.equal(options.headers.has("x-forwarded-host"), false);
    assert.equal(options.redirect, "manual");
    assert.equal(options.cache, "no-store");
    return new Response(null, {
      status: 303,
      headers: [
        ["Location", "https://identity.example/authorize"],
        ["Set-Cookie", "first=1; Secure"],
        ["Set-Cookie", "second=2; Secure"],
      ],
    });
  });
  const response = await worker.fetch(new Request(
    env.FLOWPILOT_BROWSER_ORIGIN + "//another.test/path?state=sample",
    {
      method: "POST",
      body: "sample",
      headers: {
        "Origin": env.FLOWPILOT_BROWSER_ORIGIN,
        "Cookie": "example=value",
        "Forwarded": "host=spoofed.test",
        "X-Forwarded-Host": "spoofed.test",
        "X-FlowPilot-Proxy-Secret": "supplied-by-client",
      },
    },
  ), env);
  assert.equal(mocked.mock.callCount(), 1);
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "https://identity.example/authorize");
  assert.deepEqual(response.headers.getSetCookie(), ["first=1; Secure", "second=2; Secure"]);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("fails before contacting an unexpected or unconfigured origin", async (t) => {
  const mocked = t.mock.method(globalThis, "fetch", async () => new Response());
  const allowed = new Request(env.FLOWPILOT_BROWSER_ORIGIN);
  assert.equal((await worker.fetch(allowed, { ...env, FLOWPILOT_PROXY_SECRET: "" })).status, 503);
  for (const invalid of [
    "http://example.test", "https://example.test:8443", "https://127.0.0.1",
    "https://[::1]", "https://inner.localhost", env.FLOWPILOT_BROWSER_ORIGIN,
  ]) {
    const response = await worker.fetch(allowed, { ...env, FLOWPILOT_UPSTREAM_ORIGIN: invalid });
    assert.equal(response.status, 503, invalid);
  }
  assert.equal((await worker.fetch(new Request("https://preview.test"), env)).status, 404);
  assert.equal(mocked.mock.callCount(), 0);
});
