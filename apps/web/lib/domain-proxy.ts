const SAFE_SEGMENT = /^[A-Za-z0-9._~:-]+$/;

function proxyError(status: number, code: string, message: string, correlationId: string) {
  return Response.json(
    { error: { code, message, details: null, correlation_id: correlationId } },
    { status, headers: { "X-Correlation-ID": correlationId } },
  );
}

export async function proxyDomainRequest(
  request: Request,
  path: string[],
  fetchImplementation: typeof fetch = fetch,
  baseUrl = process.env.FASTAPI_INTERNAL_URL,
): Promise<Response> {
  const correlationId = request.headers.get("X-Correlation-ID") ?? crypto.randomUUID();
  if (
    !baseUrl ||
    path.length === 0 ||
    path.some((segment) => segment === "." || segment === ".." || !SAFE_SEGMENT.test(segment))
  ) {
    return proxyError(400, "invalid_proxy_request", "invalid domain API path", correlationId);
  }

  const sourceUrl = new URL(request.url);
  const upstreamUrl = new URL(path.map(encodeURIComponent).join("/"), `${baseUrl.replace(/\/$/, "")}/`);
  upstreamUrl.search = sourceUrl.search;

  try {
    const headers = new Headers({
      Accept: request.headers.get("Accept") ?? "application/json",
      "X-Correlation-ID": correlationId,
    });
    const contentType = request.headers.get("Content-Type");
    if (contentType) headers.set("Content-Type", contentType);
    const hasBody = request.method !== "GET" && request.method !== "HEAD" && request.body !== null;
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
      signal: request.signal,
    };
    if (hasBody) {
      init.body = request.body;
      init.duplex = "half";
    }
    const upstream = await fetchImplementation(upstreamUrl.toString(), init);
    const responseHeaders = new Headers();
    responseHeaders.set("Content-Type", upstream.headers.get("Content-Type") ?? "application/json");
    responseHeaders.set(
      "X-Correlation-ID",
      upstream.headers.get("X-Correlation-ID") ?? correlationId,
    );
    const cacheControl = upstream.headers.get("Cache-Control");
    if (cacheControl) responseHeaders.set("Cache-Control", cacheControl);
    const responseHasNoBody = request.method === "HEAD" || [204, 205, 304].includes(upstream.status);
    return new Response(responseHasNoBody ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (request.signal.aborted) {
      return proxyError(499, "request_cancelled", "request was cancelled", correlationId);
    }
    return proxyError(
      502,
      "domain_api_unavailable",
      error instanceof Error ? error.message : "domain API is unavailable",
      correlationId,
    );
  }
}
