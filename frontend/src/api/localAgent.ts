export type LocalAgentApiConfig = {
  baseUrl?: string;
  orgId: string;
  adminKey?: string;
  agentToken?: string;
};

export type Device = {
  device_id: string;
  hostname?: string;
  approved?: boolean;
  last_seen?: string;
  agent_version?: string;
  organisation_id?: string;
};

export type DeviceTask = {
  id: string;
  query: string;
  created_at?: string;
  expires_at?: string;
  paths?: string[];
};

export type TaskSummary = {
  id: string;
  device_id: string;
  expires_at: string;
};

export type CreateTaskRequest = {
  query: string;
  paths?: string[];
  device_ids?: string[];
  expires_in_hours?: number;
};

export type CreateTaskResponse = {
  task_group_id: string;
  tasks_created: number;
  tasks: TaskSummary[];
};

export type RegisterDeviceRequest = {
  device_id: string;
  hostname: string;
  agent_version: string;
  organisation_id?: string;
};

export type RegisterDeviceResponse = {
  device_id: string;
  organisation_id: string;
  approved: boolean;
  message: string;
};

export type ApproveDeviceRequest = {
  device_id: string;
  approved: boolean;
};

export type TaskResultMatch = {
  type: string;
  value: string;
  file: string;
};

export type SubmitResultRequest = {
  task_id: string;
  device_id: string;
  status: string;
  scanned_files: number;
  matches: TaskResultMatch[];
};

export type TaskGroupResultResponse = {
  task_group_id: string;
  tasks: Array<Record<string, unknown>>;
  results: Array<Record<string, unknown>>;
};

export type TaskHistoryItem = {
  id: string;
  task_group_id?: string;
  device_id?: string;
  query?: string;
  paths?: string[];
  status: "pending" | "completed" | "expired" | string;
  created_at?: string;
  expires_at?: string;
  completed_at?: string;
  scanned_files: number;
  matches_count: number;
  pii_types: string[];
  matches: TaskResultMatch[];
};

export type ApiResult<T> = {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
};

type AuthKind = "admin" | "agent";

const DEFAULT_BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.trim() || "";

function normalizeBaseUrl(baseUrl?: string): string {
  const raw = (baseUrl || DEFAULT_BASE_URL).trim();
  return raw.replace(/\/$/, "");
}

function jsonHeaders(config: LocalAgentApiConfig, kind: "admin" | "agent") {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Org-Id": config.orgId,
  };

  if (kind === "admin" && config.adminKey) {
    headers["X-Admin-Key"] = config.adminKey;
  }

  if (kind === "agent" && config.agentToken) {
    headers.Authorization = `Bearer ${config.agentToken}`;
  }

  return headers;
}

function validateAuth(
  config: LocalAgentApiConfig,
  kind: AuthKind,
): string | null {
  if (!config.orgId?.trim()) {
    return "Organisation ID is required";
  }

  if (kind === "agent" && !config.agentToken?.trim()) {
    return "Agent token is required for device endpoints";
  }

  if (kind === "admin" && !config.adminKey?.trim()) {
    return "Admin key is required for admin endpoints";
  }

  return null;
}

async function requestJSON<T>(
  url: string,
  init: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(url, init);
    const text = await res.text();

    let data: T | null = null;
    if (text) {
      try {
        data = JSON.parse(text) as T;
      } catch {
        // Keep response body as plain error text.
      }
    }

    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        data,
        error: text || `Request failed with ${res.status}`,
      };
    }

    return { ok: true, status: res.status, data };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}

export async function registerDevice(
  config: LocalAgentApiConfig,
  payload: RegisterDeviceRequest,
): Promise<ApiResult<RegisterDeviceResponse>> {
  const validationError = validateAuth(config, "agent");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  return requestJSON<RegisterDeviceResponse>(
    `${normalizeBaseUrl(config.baseUrl)}/devices/register`,
    {
      method: "POST",
      headers: jsonHeaders(config, "agent"),
      body: JSON.stringify(payload),
    },
  );
}

export async function approveDevice(
  config: LocalAgentApiConfig,
  payload: ApproveDeviceRequest,
): Promise<ApiResult<{ device_id: string; approved: boolean }>> {
  const validationError = validateAuth(config, "admin");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  return requestJSON<{ device_id: string; approved: boolean }>(
    `${normalizeBaseUrl(config.baseUrl)}/devices/approve`,
    {
      method: "POST",
      headers: jsonHeaders(config, "admin"),
      body: JSON.stringify(payload),
    },
  );
}

export async function listDevices(
  config: LocalAgentApiConfig,
): Promise<ApiResult<{ devices: Device[] }>> {
  if (!config.orgId?.trim()) {
    return {
      ok: false,
      status: 400,
      data: null,
      error: "Organisation ID is required",
    };
  }

  const base = normalizeBaseUrl(config.baseUrl);
  const headers = { "X-Org-Id": config.orgId };

  const primaryResult = await requestJSON<{ devices: Device[] }>(
    `${base}/devices`,
    {
      method: "GET",
      headers,
    },
  );

  if (primaryResult.ok || !base.includes(":8000")) {
    return primaryResult;
  }

  if (primaryResult.status !== 401 && primaryResult.status !== 405) {
    return primaryResult;
  }

  return requestJSON<{ devices: Device[] }>(
    `${base.replace(":8000", ":8001")}/devices`,
    {
      method: "GET",
      headers,
    },
  );
}

export async function createTask(
  config: LocalAgentApiConfig,
  payload: CreateTaskRequest,
): Promise<ApiResult<CreateTaskResponse>> {
  const validationError = validateAuth(config, "admin");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  return requestJSON<CreateTaskResponse>(
    `${normalizeBaseUrl(config.baseUrl)}/tasks`,
    {
      method: "POST",
      headers: jsonHeaders(config, "admin"),
      body: JSON.stringify(payload),
    },
  );
}

export async function getDeviceTasks(
  config: LocalAgentApiConfig,
  deviceId: string,
): Promise<ApiResult<{ tasks: DeviceTask[] }>> {
  const validationError = validateAuth(config, "agent");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  const url = `${normalizeBaseUrl(config.baseUrl)}/devices/tasks?device_id=${encodeURIComponent(deviceId)}`;
  return requestJSON<{ tasks: DeviceTask[] }>(url, {
    method: "GET",
    headers: jsonHeaders(config, "agent"),
  });
}

export async function submitResult(
  config: LocalAgentApiConfig,
  payload: SubmitResultRequest,
): Promise<ApiResult<{ message: string; task_id: string }>> {
  const validationError = validateAuth(config, "agent");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  return requestJSON<{ message: string; task_id: string }>(
    `${normalizeBaseUrl(config.baseUrl)}/results`,
    {
      method: "POST",
      headers: jsonHeaders(config, "agent"),
      body: JSON.stringify(payload),
    },
  );
}

export async function getTaskGroupResults(
  config: LocalAgentApiConfig,
  taskGroupId: string,
): Promise<ApiResult<TaskGroupResultResponse>> {
  const validationError = validateAuth(config, "admin");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  const url = `${normalizeBaseUrl(config.baseUrl)}/tasks/${encodeURIComponent(taskGroupId)}/results`;
  return requestJSON<TaskGroupResultResponse>(url, {
    method: "GET",
    headers: jsonHeaders(config, "admin"),
  });
}

export async function listTasks(
  config: LocalAgentApiConfig,
  params?: { deviceId?: string; status?: string; limit?: number },
): Promise<ApiResult<{ tasks: TaskHistoryItem[] }>> {
  const validationError = validateAuth(config, "admin");
  if (validationError) {
    return { ok: false, status: 400, data: null, error: validationError };
  }

  const query = new URLSearchParams();
  if (params?.deviceId) query.set("device_id", params.deviceId);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));

  const qs = query.toString();
  const url = `${normalizeBaseUrl(config.baseUrl)}/tasks${qs ? `?${qs}` : ""}`;

  return requestJSON<{ tasks: TaskHistoryItem[] }>(url, {
    method: "GET",
    headers: jsonHeaders(config, "admin"),
  });
}
