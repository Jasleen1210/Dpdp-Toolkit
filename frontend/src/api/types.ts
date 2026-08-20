// Mock API layer for DPDP Compliance Engine
// Replace these with real API calls when backend is ready

export interface DashboardSummary {
  total_pii_locations: number;
  high_risk_datasets: number;
  pending_dsr: number;
  active_breaches: number;
  compliance_score: number;
}

export interface ActivityItem {
  id: number;
  event: string;
  status: "success" | "pending" | "error" | "warning";
  time: string;
  module: string;
}

export interface DataSource {
  id: string;
  name: string;
  type: "database" | "cloud" | "file";
  pii_count: number;
  risk: "high" | "medium" | "low";
  last_scan: string;
  status: "active" | "inactive";
}

export interface DSRRequest {
  id: string;
  type: "delete" | "access" | "update";
  subject: string;
  status: "pending" | "in_progress" | "completed" | "rejected" | "awaiting_approval" | "error" | "cancelled";
  created: string;
  created_at?: string;
  handler: "auto" | "manual" | string;
  devices?: string[];
  tasks_count?: number;
  tasks_completed?: number;
  source_types?: string[];
  target_sources?: string[];
  requires_approval?: boolean;
  source_status?: Record<string, string>;
  status_message?: string;
  cloud_error?: string;
}

export interface Vendor {
  id: string;
  name: string;
  risk_score: number;
  data_shared: string[];
  last_audit: string;
  status: "compliant" | "non_compliant" | "under_review";
}

export interface Incident {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "active" | "contained" | "resolved";
  affected_users: number;
  detected: string;
}

export interface AuditLog {
  id: string;
  action: string;
  user: string;
  timestamp: string;
  module: string;
  details: string;
}
