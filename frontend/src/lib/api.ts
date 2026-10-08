import { z } from "zod";
import type { JsonObject, Settings } from "./types";
import {
  groupingSchema,
  jobSchema,
  logSchema,
  outputSchema,
  pathsSchema,
  savedSessionSchema,
  sessionSchema,
  settingsSchema,
  snapshotSchema,
} from "./schemas";

async function request<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body)
        message =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
    } catch {
      /* Keep HTTP status for non-JSON error pages. */
    }
    throw new Error(message);
  }
  const result = schema.safeParse(await response.json());
  if (!result.success)
    throw new Error(
      `Phản hồi máy chủ không đúng cấu trúc (${path}): ${result.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ")}`,
    );
  return result.data;
}
export const api = {
  state: () => request("/state", snapshotSchema),
  settings: () => request("/settings", settingsSchema),
  jobs: () => request("/jobs", z.array(jobSchema)),
  sessions: () => request("/sessions", z.array(sessionSchema)),
  outputs: () => request("/outputs", z.array(outputSchema)),
  grouping: (size: number) => request(`/grouping?size=${size}`, groupingSchema),
  run: (action: string, options: JsonObject) =>
    request("/jobs", jobSchema, {
      method: "POST",
      body: JSON.stringify({ action, options }),
    }),
  stop: (id: string) =>
    request(`/jobs/${encodeURIComponent(id)}/stop`, jobSchema, {
      method: "POST",
    }),
  logs: (id: string, after = 0) =>
    request(
      `/jobs/${encodeURIComponent(id)}/logs?after=${after}`,
      z.array(logSchema),
    ),
  save: (ui: JsonObject) =>
    request("/sessions", savedSessionSchema, {
      method: "POST",
      body: JSON.stringify({ ui }),
    }),
  open: (id?: string) =>
    request(
      id ? `/sessions/${encodeURIComponent(id)}/open` : "/sessions/new",
      snapshotSchema,
      { method: "POST" },
    ),
  settingsSave: (settings: Settings) =>
    request("/settings", settingsSchema, {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  upload: async (kind: "inputs" | "assets", files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request(`/${kind}`, pathsSchema, { method: "POST", body });
  },
};
export const downloadUrl = (path: string) =>
  `/api/outputs/download?path=${encodeURIComponent(path)}`;
