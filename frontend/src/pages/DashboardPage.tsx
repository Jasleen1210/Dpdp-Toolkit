import { useEffect, useState } from "react";
import { useLocation, Link } from "react-router-dom";
import { fetchDashboard } from "@/api/mock";
import type { DashboardSummary, ActivityItem } from "@/api/types";
import {
  Shield,
  Database,
  FileText,
  AlertTriangle,
  TrendingUp,
} from "lucide-react";
import { motion } from "framer-motion";

function StatCard({
  label,
  value,
  icon: Icon,
  variant = "default",
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  variant?: "default" | "success" | "warning" | "destructive";
}) {
  const variants = {
    default: "border-border",
    success: "border-primary/30",
    warning: "border-warning/30",
    destructive: "border-destructive/30",
  };
  const iconVariants = {
    default: "text-muted-foreground",
    success: "text-primary",
    warning: "text-warning",
    destructive: "text-destructive",
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
      className={`bg-card border ${variants[variant]} rounded-sm p-4 sovereign-shadow`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground font-medium">
            {label}
          </p>
          <p className="text-2xl font-bold font-mono-data mt-1 text-foreground">
            {typeof value === "number" ? value.toLocaleString() : value}
          </p>
        </div>
        <Icon className={`w-5 h-5 ${iconVariants[variant]}`} />
      </div>
    </motion.div>
  );
}

const statusColors: Record<string, string> = {
  success: "bg-primary",
  pending: "bg-warning",
  error: "bg-destructive",
  warning: "bg-warning",
};

const subtabs = [
  { label: "Overview", href: "/" },
  { label: "Risk Heatmap", href: "/dashboard/risk-heatmap" },
  { label: "Recent Activity", href: "/dashboard/recent-activity" },
  { label: "Compliance Score", href: "/dashboard/compliance-score" },
  { label: "Alerts & Violations", href: "/dashboard/alerts" },
];

const riskData = [
  {
    zone: "Database – PostgreSQL Prod",
    risk: 92,
    pii: 4521,
    category: "Aadhaar, PAN, Email",
  },
  {
    zone: "Cloud – AWS S3 Documents",
    risk: 67,
    pii: 2108,
    category: "Email, Phone, Address",
  },
  {
    zone: "Database – MongoDB Analytics",
    risk: 85,
    pii: 1893,
    category: "Aadhaar, IP Address",
  },
  {
    zone: "File – CSV Legacy Exports",
    risk: 78,
    pii: 3070,
    category: "PAN, Bank Details",
  },
  { zone: "Cloud – Azure Blob Backups", risk: 34, pii: 890, category: "Email" },
  {
    zone: "API – Payment Gateway",
    risk: 88,
    pii: 1240,
    category: "PAN, Bank, UPI",
  },
  {
    zone: "Database – MySQL CRM",
    risk: 45,
    pii: 560,
    category: "Email, Phone",
  },
];

const complianceHistory = [
  { month: "Oct 2025", score: 78, audits: 3, violations: 12 },
  { month: "Nov 2025", score: 82, audits: 4, violations: 8 },
  { month: "Dec 2025", score: 85, audits: 2, violations: 6 },
  { month: "Jan 2026", score: 89, audits: 5, violations: 4 },
  { month: "Feb 2026", score: 91, audits: 3, violations: 3 },
  { month: "Mar 2026", score: 94, audits: 4, violations: 1 },
];

const alerts = [
  {
    id: "ALR-101",
    type: "critical",
    message: "Unmasked Aadhaar detected in PostgreSQL Prod – Table: users_pii",
    time: "12m ago",
    resolved: false,
  },
  {
    id: "ALR-100",
    type: "warning",
    message: "Consent expiry approaching for 342 users – Marketing purpose",
    time: "1h ago",
    resolved: false,
  },
  {
    id: "ALR-099",
    type: "critical",
    message: "DSR #438 SLA breach – Access request overdue by 2 days",
    time: "3h ago",
    resolved: false,
  },
  {
    id: "ALR-098",
    type: "info",
    message: "Vendor DataVault Corp risk score dropped below threshold",
    time: "5h ago",
    resolved: true,
  },
  {
    id: "ALR-097",
    type: "warning",
    message: "Agent KA-SOUTH-03 offline – No heartbeat for 4 hours",
    time: "4h ago",
    resolved: false,
  },
  {
    id: "ALR-096",
    type: "info",
    message: "Retention purge completed – 230 records removed",
    time: "6h ago",
    resolved: true,
  },
  {
    id: "ALR-095",
    type: "critical",
    message: "Unauthorized API access attempt from IP 103.22.xx.xx",
    time: "8h ago",
    resolved: true,
  },
];

const alertTypeColors: Record<string, string> = {
  critical: "bg-destructive/10 text-destructive",
  warning: "bg-warning/10 text-warning",
  info: "bg-primary/10 text-primary",
};

function SubtabNav() {
  const location = useLocation();
  return (
    <div className="flex gap-1 border-b border-border overflow-x-auto">
      {subtabs.map((s) => (
        <Link
          key={s.href}
          to={s.href}
          className={`px-3 py-2 text-[12px] font-medium whitespace-nowrap border-b-2 transition-colors ${
            location.pathname === s.href
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {s.label}
        </Link>
      ))}
    </div>
  );
}

function RiskBar({ value }: { value: number }) {
  const color =
    value >= 80 ? "bg-destructive" : value >= 50 ? "bg-warning" : "bg-primary";
  return (
    <div className="flex items-center gap-2">
      <progress
        value={value}
        max={100}
        className="progress-bar w-24 h-2"
        data-variant={
          color.includes("destructive")
            ? "destructive"
            : color.includes("warning")
              ? "warning"
              : "primary"
        }
        aria-label={`Risk ${value}%`}
      />
      <span className="font-mono-data text-[12px] text-foreground">
        {value}
      </span>
    </div>
  );
}

export default function DashboardPage() {
  const location = useLocation();
  const [data, setData] = useState<{
    summary: DashboardSummary;
    recent_activity: ActivityItem[];
  } | null>(null);

  useEffect(() => {
    fetchDashboard().then(setData);
  }, []);

  if (!data)
    return <div className="p-6 text-muted-foreground text-sm">Loading...</div>;
  const { summary, recent_activity } = data;
  const path = location.pathname;

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground">Dashboard</h1>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Sovereign Data Governance — Executive View
        </p>
      </div>
      <SubtabNav />

      {/* Overview */}
      {path === "/" && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <StatCard
              label="Compliance Score"
              value={`${summary.compliance_score}%`}
              icon={TrendingUp}
              variant="success"
            />
            <StatCard
              label="PII Locations"
              value={summary.total_pii_locations}
              icon={Database}
            />
            <StatCard
              label="High-Risk Datasets"
              value={summary.high_risk_datasets}
              icon={AlertTriangle}
              variant="warning"
            />
            <StatCard
              label="Pending DSR"
              value={summary.pending_dsr}
              icon={FileText}
            />
            <StatCard
              label="Active Breaches"
              value={summary.active_breaches}
              icon={Shield}
              variant={summary.active_breaches > 0 ? "destructive" : "success"}
            />
          </div>
          <div className="bg-card border border-border rounded-sm sovereign-shadow">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-foreground">
                Recent Activity
              </h2>
            </div>
            <div className="divide-y divide-border">
              {recent_activity.slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="px-4 py-2.5 flex items-center gap-3 hover:bg-muted/30 transition-colors"
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColors[item.status]}`}
                  />
                  <span className="text-[13px] text-foreground flex-1">
                    {item.event}
                  </span>
                  <span className="text-[11px] font-mono-data text-muted-foreground shrink-0">
                    {item.module}
                  </span>
                  <span className="text-[11px] font-mono-data text-muted-foreground shrink-0">
                    {item.time}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Risk Heatmap */}
      {path === "/dashboard/risk-heatmap" && (
        <div className="bg-card border border-border rounded-sm sovereign-shadow">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-[13px] font-semibold text-foreground">
              Risk Heatmap — Data Zones
            </h2>
          </div>
          <div className="divide-y divide-border">
            {riskData.map((r, i) => (
              <div
                key={i}
                className="px-4 py-3 flex items-center gap-4 hover:bg-muted/20 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-medium text-foreground truncate">
                    {r.zone}
                  </p>
                  <p className="text-[11px] text-muted-foreground font-mono-data mt-0.5">
                    {r.category}
                  </p>
                </div>
                <span className="text-[12px] font-mono-data text-muted-foreground shrink-0">
                  {r.pii.toLocaleString()} PII
                </span>
                <RiskBar value={r.risk} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Activity (full) */}
      {path === "/dashboard/recent-activity" && (
        <div className="bg-card border border-border rounded-sm sovereign-shadow">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-[13px] font-semibold text-foreground">
              All Recent Activity
            </h2>
          </div>
          <div className="divide-y divide-border">
            {recent_activity.map((item) => (
              <div
                key={item.id}
                className="px-4 py-2.5 flex items-center gap-3 hover:bg-muted/30 transition-colors"
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColors[item.status]}`}
                />
                <span className="text-[13px] text-foreground flex-1">
                  {item.event}
                </span>
                <span
                  className={`px-2 py-0.5 text-[10px] font-medium rounded-sm uppercase ${
                    item.status === "success"
                      ? "bg-primary/10 text-primary"
                      : item.status === "error"
                        ? "bg-destructive/10 text-destructive"
                        : "bg-warning/10 text-warning"
                  }`}
                >
                  {item.status}
                </span>
                <span className="text-[11px] font-mono-data text-muted-foreground shrink-0">
                  {item.module}
                </span>
                <span className="text-[11px] font-mono-data text-muted-foreground shrink-0">
                  {item.time}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compliance Score */}
      {path === "/dashboard/compliance-score" && (
        <div className="space-y-4">
          <div className="bg-card border border-primary/30 rounded-sm p-6 sovereign-shadow text-center">
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
              Current Compliance Score
            </p>
            <p className="text-5xl font-bold font-mono-data text-primary mt-2">
              {summary.compliance_score}%
            </p>
            <p className="text-[12px] text-muted-foreground mt-2">
              Based on 14,200 endpoints · Last evaluated 4m ago
            </p>
          </div>
          <div className="bg-card border border-border rounded-sm sovereign-shadow">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-[13px] font-semibold text-foreground">
                Compliance History
              </h2>
            </div>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                    Month
                  </th>
                  <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                    Score
                  </th>
                  <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                    Audits
                  </th>
                  <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                    Violations
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {complianceHistory.map((c) => (
                  <tr key={c.month} className="hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-mono-data text-foreground">
                      {c.month}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono-data text-primary font-medium">
                      {c.score}%
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono-data text-muted-foreground">
                      {c.audits}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono-data text-foreground">
                      {c.violations}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alerts */}
      {path === "/dashboard/alerts" && (
        <div className="bg-card border border-border rounded-sm sovereign-shadow">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h2 className="text-[13px] font-semibold text-foreground">
              Alerts & Violations
            </h2>
            <span className="text-[11px] font-mono-data text-muted-foreground">
              {alerts.filter((a) => !a.resolved).length} UNRESOLVED
            </span>
          </div>
          <div className="divide-y divide-border">
            {alerts.map((a) => (
              <div
                key={a.id}
                className={`px-4 py-3 flex items-start gap-3 hover:bg-muted/20 transition-colors ${a.resolved ? "opacity-50" : ""}`}
              >
                <span
                  className={`mt-0.5 px-2 py-0.5 text-[10px] font-medium rounded-sm uppercase shrink-0 ${alertTypeColors[a.type]}`}
                >
                  {a.type}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] text-foreground">{a.message}</p>
                  <p className="text-[11px] font-mono-data text-muted-foreground mt-0.5">
                    {a.id} · {a.time}
                  </p>
                </div>
                <span
                  className={`text-[11px] font-mono-data shrink-0 ${a.resolved ? "text-primary" : "text-warning"}`}
                >
                  {a.resolved ? "RESOLVED" : "OPEN"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
