function canonicalHttps(value) {
  try {
    const url = new URL(value);
    const dns = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
    if (url.protocol === "https:" && url.origin === value && !url.port &&
        url.hostname.length <= 253 && dns.test(url.hostname) &&
        !url.hostname.endsWith(".localhost")) {
      return url;
    }
    return null;
  } catch {
    return null;
  }
}

export default {
  async fetch(request, env) {
    const publicOrigin = canonicalHttps(env.FLOWPILOT_BROWSER_ORIGIN);
    const upstream = canonicalHttps(env.FLOWPILOT_UPSTREAM_ORIGIN);
    const secret = env.FLOWPILOT_PROXY_SECRET;
    const responseHeaders = { "Cache-Control": "no-store" };
    if (!publicOrigin || !upstream || publicOrigin.origin === upstream.origin ||
        typeof secret !== "string" || secret.length !== 64 || !/^[a-f0-9]{64}$/.test(secret)) {
      return new Response("Proxy unavailable", { status: 503, headers: responseHeaders });
    }
    const incoming = new URL(request.url);
    if (incoming.origin !== publicOrigin.origin || request.headers.has("upgrade")) {
      return new Response("Not found", { status: 404, headers: responseHeaders });
    }

    // Assign path and query without letting a path beginning with // choose a host.
    upstream.pathname = incoming.pathname;
    upstream.search = incoming.search;
    const headers = new Headers(request.headers);
    for (const name of [...headers.keys()]) {
      if (name === "host" || name === "forwarded" || name.startsWith("x-forwarded-")) {
        headers.delete(name);
      }
    }
    headers.set("X-FlowPilot-Proxy-Secret", secret);
    try {
      const response = await fetch(upstream, {
        method: request.method,
        headers,
        body: request.body,
        duplex: "half",
        redirect: "manual",
        cache: "no-store",
      });
      const outgoing = new Response(response.body, response);
      outgoing.headers.set("Cache-Control", "no-store");
      return outgoing;
    } catch {
      return new Response("Proxy unavailable", { status: 502, headers: responseHeaders });
    }
  },
};
