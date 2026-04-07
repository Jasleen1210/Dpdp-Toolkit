import {
  LayoutDashboard,
  Database,
  FileText,
  Shield,
  CheckSquare,
  Clock,
  AlertTriangle,
  Users,
  ClipboardList,
  Server,
  Settings,
  FolderSearch,
  LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  subtabs: { label: string; href: string }[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    label: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
    subtabs: [
      { label: "Overview", href: "/" },
      { label: "Risk Heatmap", href: "/dashboard/risk-heatmap" },
      { label: "Recent Activity", href: "/dashboard/recent-activity" },
      { label: "Compliance Score", href: "/dashboard/compliance-score" },
      { label: "Alerts & Violations", href: "/dashboard/alerts" },
    ],
  },
  {
    label: "Access Data",
    href: "/access-data",
    icon: FolderSearch,
    subtabs: [
      { label: "Local Files", href: "/access-data?tab=local" },
      { label: "Database", href: "/access-data?tab=db" },
      { label: "Cloud Storage", href: "/access-data?tab=cloud" },
    ],
  },
  {
    label: "Data Inventory",
    href: "/data-inventory",
    icon: Database,
    subtabs: [
      { label: "PII Index", href: "/data-inventory" },
      { label: "Data Sources", href: "/data-inventory/sources" },
      { label: "Scan Jobs", href: "/data-inventory/scans" },
      { label: "Classification Rules", href: "/data-inventory/classification" },
      { label: "Sensitive Data Map", href: "/data-inventory/map" },
    ],
  },
  {
    label: "Requests (DSR)",
    href: "/requests",
    icon: FileText,
    subtabs: [
      { label: "All Requests", href: "/requests" },
      { label: "Delete Requests", href: "/requests/delete" },
      { label: "Access Requests", href: "/requests/access" },
      { label: "Correction Requests", href: "/requests/correction" },
      { label: "Workflow Queue", href: "/requests/queue" },
    ],
  },
  {
    label: "Data Protection",
    href: "/protection",
    icon: Shield,
    subtabs: [
      { label: "Masking Policies", href: "/protection" },
      { label: "Anonymization Jobs", href: "/protection/anonymization" },
      { label: "Tokenization Vault", href: "/protection/tokenization" },
      { label: "Transformation Logs", href: "/protection/logs" },
    ],
  },
  {
    label: "Consent",
    href: "/consent",
    icon: CheckSquare,
    subtabs: [
      { label: "Consent Ledger", href: "/consent" },
      { label: "Purpose Management", href: "/consent/purposes" },
      { label: "Consent Policies", href: "/consent/policies" },
      { label: "API Access Logs", href: "/consent/api-logs" },
    ],
  },
  {
    label: "Retention",
    href: "/retention",
    icon: Clock,
    subtabs: [
      { label: "Retention Policies", href: "/retention" },
      { label: "Expiry Tracker", href: "/retention/expiry" },
      { label: "Auto-Purge Jobs", href: "/retention/purge" },
      { label: "Archive Vault", href: "/retention/archive" },
    ],
  },
  {
    label: "Incidents",
    href: "/incidents",
    icon: AlertTriangle,
    subtabs: [
      { label: "Active Incidents", href: "/incidents" },
      { label: "Breach Analyzer", href: "/incidents/analyzer" },
      { label: "Impacted Users", href: "/incidents/users" },
      { label: "Notifications", href: "/incidents/notifications" },
      { label: "SIEM Integrations", href: "/incidents/siem" },
    ],
  },
  {
    label: "Third Parties",
    href: "/third-parties",
    icon: Users,
    subtabs: [
      { label: "Vendor Registry", href: "/third-parties" },
      { label: "Data Sharing Logs", href: "/third-parties/sharing" },
      { label: "Risk Scores", href: "/third-parties/risk" },
      { label: "Revocation Requests", href: "/third-parties/revocation" },
    ],
  },
  {
    label: "Audit & Reports",
    href: "/audit",
    icon: ClipboardList,
    subtabs: [
      { label: "Audit Logs", href: "/audit" },
      { label: "Compliance Reports", href: "/audit/reports" },
      { label: "Regulator Exports", href: "/audit/exports" },
      { label: "Forensic Timeline", href: "/audit/timeline" },
    ],
  },
  {
    label: "Infrastructure",
    href: "/infrastructure",
    icon: Server,
    subtabs: [
      { label: "Agents (Endpoints)", href: "/infrastructure" },
      { label: "Cloud Connectors", href: "/infrastructure/cloud" },
      { label: "Database Connectors", href: "/infrastructure/database" },
      { label: "Scan Status", href: "/infrastructure/scan-status" },
      { label: "Policy Deployment", href: "/infrastructure/deployment" },
    ],
  },
  {
    label: "Settings",
    href: "/settings",
    icon: Settings,
    subtabs: [
      { label: "Users & Roles", href: "/settings" },
      { label: "API Keys", href: "/settings/api-keys" },
      { label: "Security Settings", href: "/settings/security" },
      { label: "Integrations", href: "/settings/integrations" },
      { label: "Notifications", href: "/settings/notifications" },
      { label: "Organization Profile", href: "/settings/organization" },
    ],
  },
];
