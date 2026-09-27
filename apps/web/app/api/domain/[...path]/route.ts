import { proxyDomainRequest } from "@/lib/domain-proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  return proxyDomainRequest(request, path);
}

export const POST = GET;
export const PUT = GET;
export const PATCH = GET;
export const DELETE = GET;
