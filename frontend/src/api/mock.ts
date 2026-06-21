import type {
  DashboardSummary,
  ActivityItem,
  DataSource,
  DSRRequest,
  Vendor,
  Incident,
  AuditLog,
} from "./types";

// Simulated network delay
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function fetchDashboard(): Promise<{
  summary: DashboardSummary;
  recent_activity: ActivityItem[];
}> {
  await delay(300);
  return {
    summary: {
      total_pii_locations: 12482,
      high_risk_datasets: 14,
      pending_dsr: 89,
      active_breaches: 0,
      compliance_score: 94,
    },
    recent_activity: [
      {
        id: 1,
        event: "Aadhaar Scan Complete",
        status: "success",
        time: "2m ago",
        module: "Data Inventory",
      },
      {
        id: 2,
        event: "DSR Request #442 Created",
        status: "pending",
        time: "15m ago",
        module: "Requests",
      },
      {
        id: 3,
        event: "Masking Policy Applied – DB-04",
        status: "success",
        time: "32m ago",
        module: "Data Protection",
      },
      {
        id: 4,
        event: "Consent Revoked – User #8812",
        status: "warning",
        time: "1h ago",
        module: "Consent",
      },
      {
        id: 5,
        event: "Retention Purge Executed",
        status: "success",
        time: "2h ago",
        module: "Retention",
      },
      {
        id: 6,
        event: "Vendor Risk Score Updated",
        status: "pending",
        time: "3h ago",
        module: "Third Parties",
      },
      {
        id: 7,
        event: "Agent KA-SOUTH-03 Offline",
        status: "error",
        time: "4h ago",
        module: "Infrastructure",
      },
      {
        id: 8,
        event: "Compliance Report Generated",
        status: "success",
        time: "5h ago",
        module: "Audit",
      },
    ],
  };
}

export async function fetchDataSources(): Promise<DataSource[]> {
  await delay(200);
  return [
    {
      id: "ds-1",
      name: "PostgreSQL – Production",
      type: "database",
      pii_count: 4521,
      risk: "high",
      last_scan: "4m ago",
      status: "active",
    },
    {
      id: "ds-2",
      name: "AWS S3 – Documents",
      type: "cloud",
      pii_count: 2108,
      risk: "medium",
      last_scan: "12m ago",
      status: "active",
    },
    {
      id: "ds-3",
      name: "MongoDB – Analytics",
      type: "database",
      pii_count: 1893,
      risk: "high",
      last_scan: "1h ago",
      status: "active",
    },
    {
      id: "ds-4",
      name: "Azure Blob – Backups",
      type: "cloud",
      pii_count: 890,
      risk: "low",
      last_scan: "2h ago",
      status: "active",
    },
    {
      id: "ds-5",
      name: "CSV Exports – Legacy",
      type: "file",
      pii_count: 3070,
      risk: "high",
      last_scan: "6h ago",
      status: "inactive",
    },
  ];
}

// export async function fetchDSRRequests(): Promise<DSRRequest[]> {
//   await delay(200);
//   return [
//     { id: "DSR-442", type: "delete", subject: "user@example.com", status: "pending", created: "15m ago", sla_remaining: "29d 23h", handler: "auto" },
//     { id: "DSR-441", type: "access", subject: "XXXX-XXXX-8891", status: "in_progress", created: "2h ago", sla_remaining: "28d 12h", handler: "manual" },
//     { id: "DSR-440", type: "correction", subject: "admin@corp.in", status: "completed", created: "1d ago", sla_remaining: "—", handler: "auto" },
//     { id: "DSR-439", type: "delete", subject: "XXXX-XXXX-2234", status: "pending", created: "1d ago", sla_remaining: "27d 8h", handler: "manual" },
//     { id: "DSR-438", type: "access", subject: "legal@firm.co.in", status: "rejected", created: "3d ago", sla_remaining: "—", handler: "manual" },
//   ];
// }

export async function fetchVendors(): Promise<Vendor[]> {
  await delay(200);
  return [
    {
      id: "v-1",
      name: "CloudSync Analytics",
      risk_score: 82,
      data_shared: ["Aadhaar", "Email"],
      last_audit: "2d ago",
      status: "compliant",
    },
    {
      id: "v-2",
      name: "PayGate India",
      risk_score: 45,
      data_shared: ["PAN", "Bank Details"],
      last_audit: "15d ago",
      status: "under_review",
    },
    {
      id: "v-3",
      name: "MailJet Comms",
      risk_score: 91,
      data_shared: ["Email", "Phone"],
      last_audit: "5d ago",
      status: "compliant",
    },
    {
      id: "v-4",
      name: "DataVault Corp",
      risk_score: 28,
      data_shared: ["Aadhaar", "Address"],
      last_audit: "30d ago",
      status: "non_compliant",
    },
  ];
}

export async function fetchIncidents(): Promise<Incident[]> {
  await delay(200);
  return [
    {
      id: "INC-101",
      title: "Unauthorized Access – DB-04",
      severity: "high",
      status: "contained",
      affected_users: 342,
      detected: "2h ago",
    },
    {
      id: "INC-100",
      title: "Data Exfiltration Attempt",
      severity: "critical",
      status: "active",
      affected_users: 0,
      detected: "30m ago",
    },
    {
      id: "INC-099",
      title: "Misconfigured S3 Bucket",
      severity: "medium",
      status: "resolved",
      affected_users: 1200,
      detected: "3d ago",
    },
  ];
}

export async function fetchAuditLogs(): Promise<AuditLog[]> {
  await delay(200);
  return [
    {
      id: "log-1",
      action: "POLICY_APPLIED",
      user: "admin@dpdp.gov.in",
      timestamp: "2025-03-18 14:32:01",
      module: "Data Protection",
      details: "Masking policy MP-04 applied to PostgreSQL Production",
    },
    {
      id: "log-2",
      action: "DSR_CREATED",
      user: "system",
      timestamp: "2025-03-18 14:15:44",
      module: "Requests",
      details: "Auto-created DSR #442 from portal submission",
    },
    {
      id: "log-3",
      action: "SCAN_COMPLETED",
      user: "scanner-agent-01",
      timestamp: "2025-03-18 14:10:22",
      module: "Data Inventory",
      details: "Full PII scan on PostgreSQL Production – 4521 records",
    },
    {
      id: "log-4",
      action: "CONSENT_REVOKED",
      user: "user@example.com",
      timestamp: "2025-03-18 13:45:00",
      module: "Consent",
      details: "User revoked marketing consent via API",
    },
    {
      id: "log-5",
      action: "PURGE_EXECUTED",
      user: "scheduler",
      timestamp: "2025-03-18 12:00:00",
      module: "Retention",
      details: "Auto-purge: 230 records past retention period",
    },
  ];
}
