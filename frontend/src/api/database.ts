export type DatabaseEngine = "sqlite" | "postgres";

export type OrganisationSummary = {
  id: string;
  name: string;
  role?: string;
};

export type DatabaseSource = {
  id: string;
  organisation_id: string;
  display_name: string;
  engine: DatabaseEngine;
  connection_label: string;
  credential_configured: boolean;
  created_at?: string;
  updated_at?: string;
  last_scan_at?: string | null;
  last_scan_status?: string;
  latest_summary?: DatabaseSummary;
};

export type DatabaseSummary = {
  finding_count?: number;
  pii_instance_count?: number;
  critical_finding_count?: number;
  high_finding_count?: number;
  scanned_tables?: number;
  inspected_columns?: number;
  sampled_values?: number;
  warning_count?: number;
};

export type DatabaseFinding = {
  id?: string;
  source_type: "database";
  engine: DatabaseEngine;
  table: string;
  column: string;
  column_type: string;
  location: string;
  pii_type: string;
  confidence: number;
  sample_count: number;
  match_count: number;
  method: "metadata" | "regex" | "metadata+regex";
  risk: "low" | "medium" | "high" | "critical";
  risk_rank: number;
  recommended_action: string;
};

export type DatabaseScanRun = {
  id: string;
  source_id: string;
  organisation_id: string;
  status: string;
  started_at?: string;
  completed_at?: string | null;
  summary?: DatabaseSummary;
  error?: string | null;
};

export type DatabaseScanResponse = {
  source: DatabaseSource;
  run: DatabaseScanRun;
  summary: DatabaseSummary;
  warnings: string[];
  findings: DatabaseFinding[];
};

const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) || ""
).replace(/\/$/, "");

async function readResponse<T>(response: Response): Promise<T> {
  const text = await response.text();

  let body: T | { detail?: string } = {} as T;

  if (text) {
    try {
      body = JSON.parse(text) as T;
    } catch {
      body = { detail: text };
    }
  }

  if (!response.ok) {
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || `Request failed (${response.status}).`);
  }

  return body as T;
}

async function request<T>(
  path: string,
  token: string | null,
  options: RequestInit = {},
): Promise<T> {
  if (!API_BASE) {
    throw new Error("VITE_API_URL is required in frontend/.env.");
  }

  if (!token) {
    throw new Error("Please sign in before using database discovery.");
  }

  const headers = new Headers(options.headers);

  headers.set("Authorization", `Bearer ${token}`);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  return readResponse<T>(response);
}

export async function listMyOrganisations(
  token: string | null,
): Promise<{ organisations: OrganisationSummary[] }> {
  return request<{ organisations: OrganisationSummary[] }>(
    "/auth/organisations/mine",
    token,
  );
}

export async function listDatabaseSources(
  token: string | null,
  organisationId: string,
): Promise<{ sources: DatabaseSource[] }> {
  return request<{ sources: DatabaseSource[] }>(
    `/database/sources?organisation_id=${encodeURIComponent(organisationId)}`,
    token,
  );
}

/**
 * Registers the Supabase PostgreSQL source using credentials
 * already configured in the backend environment.
 *
 * No database password is ever sent by the browser.
 */
export async function createConfiguredSupabaseSource(
  token: string | null,
  organisationId: string,
): Promise<{ source: DatabaseSource }> {
  return request<{ source: DatabaseSource }>(
    `/database/sources/configured-supabase?organisation_id=${encodeURIComponent(
      organisationId,
    )}`,
    token,
    {
      method: "POST",
    },
  );
}

export async function scanDatabaseSource(
  token: string | null,
  organisationId: string,
  sourceId: string,
): Promise<DatabaseScanResponse> {
  return request<DatabaseScanResponse>(
    `/database/sources/${encodeURIComponent(
      sourceId,
    )}/scan?organisation_id=${encodeURIComponent(organisationId)}`,
    token,
    {
      method: "POST",
    },
  );
}

export async function getDatabaseFindings(
  token: string | null,
  organisationId: string,
  sourceId: string,
): Promise<{
  source: DatabaseSource;
  findings: DatabaseFinding[];
}> {
  return request<{
    source: DatabaseSource;
    findings: DatabaseFinding[];
  }>(
    `/database/sources/${encodeURIComponent(
      sourceId,
    )}/findings?organisation_id=${encodeURIComponent(organisationId)}`,
    token,
  );
}