import { describe, expect, it, vi } from "vitest";

import { proxyDomainRequest } from "./domain-proxy";


describe("domain proxy", () => {
  it("forwards correlation id and preserves typed errors", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(new Headers(init.headers).get("X-Correlation-ID")).toBe("trace-42");
      return new Response(
        JSON.stringify({ error: { code: "model_not_found", message: "missing" } }),
        {
          status: 404,
          headers: { "content-type": "application/json", "x-correlation-id": "trace-42" },
        },
      );
    });
    const request = new Request("http://web/api/domain/v1/models/missing", {
      headers: { "X-Correlation-ID": "trace-42" },
    });

    const response = await proxyDomainRequest(
      request,
      ["v1", "models", "missing"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.status).toBe(404);
    expect(response.headers.get("X-Correlation-ID")).toBe("trace-42");
    await expect(response.json()).resolves.toMatchObject({ error: { code: "model_not_found" } });
  });

  it("forwards colon-delimited command resources", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      expect(url).toBe("http://api:8000/v1/models/model-1/surface-regions%3Adetect");
      return Response.json({ source: "explicit_surface_polygon" });
    });
    const request = new Request("http://web/api/domain/v1/models/model-1/surface-regions:detect", {
      method: "POST",
      body: JSON.stringify({ x: 1, y: 2 }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await proxyDomainRequest(
      request,
      ["v1", "models", "model-1", "surface-regions:detect"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.status).toBe(200);
  });

  it("rejects path traversal before upstream call", async () => {
    const fetchMock = vi.fn();
    const request = new Request("http://web/api/domain/invalid");

    const response = await proxyDomainRequest(
      request,
      ["v1", "..", "openapi.json"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not forward browser cookies or authorization to the domain API", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const headers = new Headers(init.headers);
      expect(headers.has("cookie")).toBe(false);
      expect(headers.has("authorization")).toBe(false);
      return Response.json({ items: [] });
    });
    const request = new Request("http://web/api/domain/v1/projects", {
      headers: { cookie: "session=secret", authorization: "Bearer browser-secret" },
    });

    await proxyDomainRequest(
      request,
      ["v1", "projects"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("streams a multipart POST body without forwarding browser credentials", async () => {
    const form = new FormData();
    form.set("relative_path", "plans/master.dxf");
    form.set("file", new Blob(["DXF"]), "master.dxf");
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.method).toBe("POST");
      const headers = new Headers(init.headers);
      expect(headers.get("content-type")).toContain("multipart/form-data");
      expect(headers.has("cookie")).toBe(false);
      expect(headers.has("authorization")).toBe(false);
      expect(init.body).toBeTruthy();
      return Response.json({ asset_id: "asset-1" }, { status: 201 });
    });
    const request = new Request("http://web/api/domain/v1/intake/projects/p1/files", {
      method: "POST",
      headers: { cookie: "session=secret", authorization: "Bearer secret" },
      body: form,
    });

    const response = await proxyDomainRequest(
      request,
      ["v1", "intake", "projects", "p1", "files"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.status).toBe(201);
  });

  it("forwards project soft delete without inventing a request body", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.method).toBe("DELETE");
      expect(init.body).toBeUndefined();
      return new Response(null, { status: 204 });
    });
    const request = new Request("http://web/api/domain/v1/intake/projects/project-1", {
      method: "DELETE",
    });

    const response = await proxyDomainRequest(
      request,
      ["v1", "intake", "projects", "project-1"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("forwards private cache policy for immutable model geometry", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", {
      headers: { "Cache-Control": "private, max-age=300, stale-while-revalidate=3600" },
    }));
    const request = new Request("http://web/api/domain/v1/models/model-1/features?bbox=0,0,1,1");

    const response = await proxyDomainRequest(
      request,
      ["v1", "models", "model-1", "features"],
      fetchMock as typeof fetch,
      "http://api:8000",
    );

    expect(response.headers.get("Cache-Control"))
      .toBe("private, max-age=300, stale-while-revalidate=3600");
  });
});
