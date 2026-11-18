"use client";

import type { z } from "zod";
import { getAccount } from "@/lib/auth";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_PREFIX = "/api/v1";
const TIMEOUT_MS = 30_000;

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

type Query = Record<string, string | number | boolean | undefined | null>;

export interface RequestOptions<S extends z.ZodTypeAny, R = z.output<S>> {
  /** Schema of the backend response (what the API actually returns). */
  schema: S;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  /** Turns the validated backend response into what the screen renders. */
  map?: (data: z.output<S>) => R;
}

function withQuery(path: string, query?: Query) {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}${path.includes("?") ? "&" : "?"}${text}` : path;
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

async function send(path: string, init: { method: string; body?: BodyInit; headers?: Record<string, string> }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${API_PREFIX}${path}`, {
      method: init.method,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Accept-Language": language(),
        "X-API-Key": getAccount()?.key ?? "",
        ...init.headers,
      },
      body: init.body,
    });
    if (!res.ok) throw await toApiError(res);
    return res;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, "network", "Server bilan aloqa yo‘q");
  } finally {
    clearTimeout(timer);
  }
}

/** Calls the backend. There is no fallback: a failed call or an unexpected shape is an error the screen shows. */
export async function api<S extends z.ZodTypeAny, R = z.output<S>>(path: string, options: RequestOptions<S, R>): Promise<R> {
  const { schema, method = "GET", body, query, map } = options;
  const res = await send(withQuery(path, query), {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const json = res.status === 204 ? {} : await res.json();
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    console.error(`Unexpected response shape from ${method} ${path}`, parsed.error.issues);
    throw new ApiError(502, "bad_shape", "Javob kutilgan ko‘rinishda emas", parsed.error.issues);
  }
  return map ? map(parsed.data) : (parsed.data as R);
}

/** Multipart upload (files). */
export async function upload<S extends z.ZodTypeAny, R = z.output<S>>(path: string, form: FormData, options: Omit<RequestOptions<S, R>, "body" | "method">): Promise<R> {
  const { schema, query, map } = options;
  const res = await send(withQuery(path, query), { method: "POST", body: form });
  const parsed = schema.safeParse(await res.json());
  if (!parsed.success) {
    console.error(`Unexpected response shape from POST ${path}`, parsed.error.issues);
    throw new ApiError(502, "bad_shape", "Javob kutilgan ko‘rinishda emas", parsed.error.issues);
  }
  return map ? map(parsed.data) : (parsed.data as R);
}

/** Downloads a file the backend generates (exports, documents). */
export async function download(path: string, filename: string, query?: Query) {
  const res = await send(withQuery(path, query), { method: "GET" });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
