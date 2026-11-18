export const dynamic = "force-dynamic";

export async function GET() {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/openapi.json`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    return Response.json({ up: res.ok });
  } catch {
    return Response.json({ up: false });
  }
}
