"use client";

import type { z } from "zod";
import { getAccount } from "@/lib/auth";
import { mockRequest } from "./fixtures/server";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_PREFIX = "/api/v1";
const FIXTURE_MODE = process.env.NEXT_PUBLIC_USE_FIXTURES ?? "auto";
const TIMEOUT_MS = 15_000;
const HEALTH_TTL_MS = 20_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type DataSource = "unknown" | "live" | "fixtures";
let source: DataSource = "unknown";
const sourceListeners = new Set<() => void>();
export const endpointSources = new Map<string, "live" | "fixtures">();

function mark(next: "live" | "fixtures", method: string, path: string) {
  endpointSources.set(`${method} ${path.split("?")[0]}`, next);
  if (next === "fixtures" && source !== "fixtures") {
    source = "fixtures";
    sourceListeners.forEach((fn) => fn());
  } else if (next === "live" && source === "unknown") {
    source = "live";
    sourceListeners.forEach((fn) => fn());
  }
}

export const dataSourceStore = {
  subscribe(fn: () => void) {
    sourceListeners.add(fn);
    return () => sourceListeners.delete(fn);
  },
  get: () => source,
  getServer: (): DataSource => "unknown",
};

let health: { up: boolean; at: number } | null = null;

/** Asks a same-origin route, so a stopped backend never logs a browser network error. */
async function backendUp() {
  if (health && Date.now() - health.at < HEALTH_TTL_MS) return health.up;
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    const body = (await res.json()) as { up: boolean };
    health = { up: body.up, at: Date.now() };
  } catch {
    health = { up: false, at: Date.now() };
  }
  return health.up;
}

export interface RequestOptions<S extends z.ZodTypeAny> {
  schema: S;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function withQuery(path: string, query?: RequestOptions<z.ZodTypeAny>["query"]) {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

function language() {
  try {
    return window.localStorage.getItem("raft_lang") ?? "uz";
  } catch {
    return "uz";
  }
}

async function toApiError(res: Response) {
  try {
    const data = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown } };
    return new ApiError(res.status, data.error?.code ?? "error", data.error?.message ?? res.statusText, data.error?.details);
  } catch {
    return new ApiError(res.status, "error", res.statusText || "So‘rov bajarilmadi");
  }
}

export async function api<S extends z.ZodTypeAny>(path: string, options: RequestOptions<S>): Promise<z.output<S>> {
  const { schema, method = "GET", body, query } = options;
  const url = withQuery(path, query);
  const auto = FIXTURE_MODE === "auto";
  const tryLive = FIXTURE_MODE === "false" || (auto && (await backendUp()));

  if (tryLive) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(`${API_URL}${API_PREFIX}${url}`, {
        method,
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          "Accept-Language": language(),
          "X-API-Key": getAccount()?.key ?? "",
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (res.ok) {
        const parsed = schema.safeParse(res.status === 204 ? { ok: true } : await res.json());
        if (parsed.success) {
          mark("live", method, path);
          return parsed.data;
        }
        if (!auto) throw new ApiError(502, "bad_shape", "Javob kutilgan ko‘rinishda emas", parsed.error.issues);
      } else if (!(auto && (res.status >= 500 || res.status === 404 || res.status === 405))) {
        throw await toApiError(res);
      }
    } catch (error) {
      if (error instanceof ApiError || !auto) {
        if (error instanceof ApiError) throw error;
        throw new ApiError(0, "network", "Server bilan aloqa yo‘q");
      }
    } finally {
      clearTimeout(timer);
    }
  }

  mark("fixtures", method, path);
  return schema.parse(await mockRequest(method, path, { body, query }));
}
