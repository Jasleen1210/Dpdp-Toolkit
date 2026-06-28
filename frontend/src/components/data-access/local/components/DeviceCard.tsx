import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { VulnerabilityTable } from "./VulnerabillityTable";
import {
  getDeviceVulnerabilities,
  type Device,
  type DeviceDailyScanReportItem,
  type LocalAgentApiConfig,
  type VulnerabilityItem,
} from "../../../../api/localAgent";

function formatDate(value?: string): string {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

interface Props {
  device: Device;
  report?: DeviceDailyScanReportItem;
  dailyReportDate: string;
  orgId: string;
  loading: boolean;
  apiConfig: LocalAgentApiConfig;
  onApprove: (deviceId: string) => void;
}

export function DeviceCard({
  device, report, dailyReportDate,
  orgId, loading, apiConfig, onApprove,
}: Props) {
  const scannedToday = !!report?.scanned_today;
  const deviceActive =
    typeof device.is_active === "boolean"
      ? device.is_active
      : (report?.is_active ?? false);

  const [vulns, setVulns] = useState<VulnerabilityItem[]>([]);
  const [vulnSummary, setVulnSummary] = useState<{
    total_vulnerabilities?: number;
    total_exposed_matches?: number;
    max_priority_score?: number;
  }>({});
  const [vulnUpdatedAt, setVulnUpdatedAt] = useState<string | undefined>();
  const [vulnLoading, setVulnLoading] = useState(false);

  useEffect(() => {
    if (!device.device_id || !apiConfig.orgId) return;
    let active = true;

    const load = async () => {
      setVulnLoading(true);
      const res = await getDeviceVulnerabilities(apiConfig, device.device_id);
      if (!active) return;
      setVulnLoading(false);
      if (res.ok && res.data) {
        setVulns(res.data.vulnerabilities || []);
        setVulnSummary(res.data.summary || {});
        setVulnUpdatedAt(res.data.updated_at);
      }
    };

    void load();
    return () => { active = false; };
  }, [device.device_id, apiConfig.orgId]);

  return (
    <div className="rounded-sm border border-border bg-muted/20 p-3 text-[12px]">
      <div className="flex items-center justify-between gap-2">
        <div className="font-medium text-foreground break-all">{device.device_id}</div>
        <div className="flex items-center gap-1">
          <span className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${
            deviceActive
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600"
              : "border-muted-foreground/30 bg-muted text-muted-foreground"
          }`}>
            {deviceActive ? "Active" : "Inactive"}
          </span>
          <span className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${
            device.approved
              ? "border-primary/30 bg-primary/15 text-primary"
              : "border-warning/30 bg-warning/15 text-warning"
          }`}>
            {device.approved ? "Approved" : "Pending"}
          </span>
          {!device.approved && (
            <Button size="sm" variant="secondary" disabled={loading}
              onClick={() => onApprove(device.device_id)}>
              Approve
            </Button>
          )}
        </div>
      </div>

      <div className="mt-2 grid gap-1 text-muted-foreground">
        <div>Hostname: <span className="text-foreground">{device.hostname || "-"}</span></div>
        <div>Version: <span className="text-foreground">{device.agent_version || "-"}</span></div>
        <div>Activity Window: <span className="text-foreground">{device.active_window_seconds || 180}s</span></div>
        <div>Org: <span className="text-foreground">{device.organisation_id || orgId}</span></div>
        <div>Last Seen: <span className="text-foreground">{formatDate(device.last_seen)}</span></div>

        <div className="mt-2 rounded-sm border border-border bg-background/70 px-2 py-2 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Daily Scan Report {dailyReportDate ? `(${dailyReportDate})` : ""}
            </div>
            <span className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${
              scannedToday
                ? "border-primary/30 bg-primary/15 text-primary"
                : "border-muted-foreground/30 bg-muted text-muted-foreground"
            }`}>
              {scannedToday ? "Scanned Today" : "Not Scanned"}
            </span>
          </div>
          <div>Last Daily Scan: <span className="text-foreground">{formatDate(report?.last_scan_at)}</span></div>
          <div>
            Scanned Files: <span className="text-foreground">{report?.scanned_files ?? 0}</span>
            {" | "}
            Matches: <span className="text-foreground">{report?.matches_count ?? 0}</span>
          </div>
          {report?.pii_types?.length ? (
            <div className="flex flex-wrap gap-1 pt-1">
              {report.pii_types.map((t) => (
                <span key={`${device.device_id}-daily-${t}`}
                  className="px-2 py-0.5 text-[10px] bg-primary/15 text-primary border border-primary/30 rounded-sm">
                  {t}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        {/* Vulnerability table sits below daily scan report */}
        <VulnerabilityTable
          vulnerabilities={vulns}
          summary={vulnSummary}
          updatedAt={vulnUpdatedAt}
          loading={vulnLoading}
        />
      </div>
    </div>
  );
}