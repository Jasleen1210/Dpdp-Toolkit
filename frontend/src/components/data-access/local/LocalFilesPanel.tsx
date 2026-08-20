import React, { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { ChevronDown, RefreshCw } from "lucide-react";
import {
  approveDevice,
  getCronRunVulnerabilities,
  getMyOrganisations,
  listCronRuns,
  listDeviceApprovalRequests,
  listDeviceDailyScanReports,
  listOrganisationDevices,
  type CronRunItem,
  type CronRunVulnerabilitiesResponse,
  type Device,
  type DeviceApprovalRequestItem,
  type DeviceDailyScanReportItem,
  type OrganisationInfo,
} from "../../../api/localAgent";
import { Button } from "@/components/ui/button";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { setOrganisations } from "@/redux/authSlice";
import { DeviceCard } from "./components/DeviceCard";
import { OrgDetailsPanel } from "./components/OrgDetailsPanel";

type ActiveTab = "devices" | "cron";
type CronRunDetailState = {
  status: "loading" | "loaded" | "error";
  data?: CronRunVulnerabilitiesResponse;
  error?: string;
};

const MAX_RENDERED_CRON_FINDINGS = 100;

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function normalizeStatus(status?: string | null): string {
  return status?.toLowerCase() || "";
}

function statusClass(status?: string | null): string {
  const normalized = normalizeStatus(status);
  if (normalized === "completed") return "bg-primary/15 text-primary border-primary/30";
  if (normalized === "failed") return "bg-destructive/15 text-destructive border-destructive/30";
  if (normalized === "started" || normalized === "pending") {
    return "bg-warning/15 text-warning border-warning/30";
  }
  return "bg-muted text-muted-foreground border-border";
}


function formatDuration(
  value?: string | null,
  status?: string | null,
  completedAt?: string | null,
): string {
  if (value?.trim()) return value.trim();
  const normalizedStatus = normalizeStatus(status);
  const finished = Boolean(completedAt) || [
    "completed",
    "failed",
    "cancelled",
    "finished",
    "success",
    "succeeded",
  ].includes(normalizedStatus);
  return finished ? "-" : "In progress";
}

function findingPriorityClass(score?: number | null): string {
  if (typeof score !== "number") return "bg-muted text-muted-foreground border-border";
  if (score >= 0.8) return "bg-destructive/10 text-destructive border-destructive/30";
  if (score >= 0.6) return "bg-warning/10 text-warning border-warning/30";
  return "bg-primary/10 text-primary border-primary/30";
}

function shortenFindingPath(path?: string | null): string {
  if (!path) return "-";
  const parts = path.split(/[/\\]/);
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export default function LocalFilesPanel() {
  const dispatch = useAppDispatch();
  const [activeTab, setActiveTab] = useState<ActiveTab>("devices");
  const authOrgs = useAppSelector((s) => s.auth.organisations);
  const authToken = useAppSelector((s) => s.auth.token);
  const authMode = useAppSelector((s) => s.auth.mode);

  const envBaseUrl = ((import.meta.env.VITE_API_URL as string | undefined) || "http://127.0.0.1:8010").trim();
  const [baseUrl] = useState(envBaseUrl);

  const [orgId, setOrgId] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [agentToken, setAgentToken] = useState("");
  const [orgName, setOrgName] = useState("");
  const [orgs, setOrgs] = useState<OrganisationInfo[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [orgDetailsOpen, setOrgDetailsOpen] = useState(false);
  const [orgsLoading, setOrgsLoading] = useState(false);

  const [devices, setDevices] = useState<Device[]>([]);
  const [dailyReportDate, setDailyReportDate] = useState("");
  const [dailyReportByDevice, setDailyReportByDevice] = useState<Record<string, DeviceDailyScanReportItem>>({});
  const [approvalRequests, setApprovalRequests] = useState<DeviceApprovalRequestItem[]>([]);
  const [cronRuns, setCronRuns] = useState<CronRunItem[]>([]);
  const [cronFilterDeviceId, setCronFilterDeviceId] = useState("");
  const [expandedCronRunIds, setExpandedCronRunIds] = useState<Set<string>>(new Set());
  const [cronRunDetails, setCronRunDetails] = useState<Record<string, CronRunDetailState>>({});
  const cronRunRequestIds = useRef<Record<string, number>>({});
  const mountedRef = useRef(true);

  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListingDevices, setIsListingDevices] = useState(false);
  const [isListingCronRuns, setIsListingCronRuns] = useState(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const normalizedBaseUrl = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);
  const apiConfig = useMemo(() => ({
    baseUrl: normalizedBaseUrl,
    orgId: orgId.trim(),
    adminKey: adminKey.trim(),
    agentToken: agentToken.trim(),
  }), [normalizedBaseUrl, orgId, adminKey, agentToken]);

  const localDevices = useMemo(
    () => devices.filter((device) => device.source_type === "local_device"),
    [devices],
  );
  const deviceById = useMemo(
    () => new Map(localDevices.map((device) => [device.device_id, device])),
    [localDevices],
  );
  const scannedTodayCount = useMemo(
    () => localDevices.filter((device) => dailyReportByDevice[device.device_id]?.scanned_today).length,
    [localDevices, dailyReportByDevice],
  );
  const completedCronRuns = useMemo(
    () => cronRuns.filter((run) => normalizeStatus(run.status) === "completed").length,
    [cronRuns],
  );
  const failedCronRuns = useMemo(
    () => cronRuns.filter((run) => normalizeStatus(run.status) === "failed").length,
    [cronRuns],
  );

  const clearMessages = () => { setStatusText(""); setErrorText(""); };

  useEffect(() => {
    if ((authOrgs || []).length > 0) { setOrgs(authOrgs); return; }
    if (authMode === "guest" || !authToken?.trim() || !baseUrl.trim()) { setOrgs([]); return; }

    let active = true;
    const hydrate = async () => {
      setOrgsLoading(true);
      const res = await getMyOrganisations({ baseUrl, orgId: "", adminKey: "", agentToken: "" }, authToken);
      if (!active) return;
      setOrgsLoading(false);
      if (!res.ok || !res.data?.organisations) return;
      setOrgs(res.data.organisations);
      dispatch(setOrganisations(res.data.organisations));
    };
    void hydrate();
    return () => { active = false; };
  }, [authOrgs, authMode, authToken, baseUrl, dispatch]);

  useEffect(() => {
    if (!orgs.length) {
      setSelectedOrgId(""); setOrgId(""); setOrgName(""); setAdminKey(""); setAgentToken("");
      return;
    }
    const selected = orgs.find((o) => o.id === selectedOrgId) || orgs[0];
    setSelectedOrgId(selected.id);
    setOrgId(selected.id);
    setOrgName(selected.name || "");
    setAdminKey(selected.admin_api_key || "");
    setAgentToken(selected.agent_token || "");
  }, [orgs, selectedOrgId]);

  const refreshDevices = useCallback(async (showPlaceholder = true): Promise<Device[]> => {
    if (showPlaceholder) setIsListingDevices(true);
    const res = await listOrganisationDevices(apiConfig, orgId);
    if (showPlaceholder) setIsListingDevices(false);
    if (!res.ok || !res.data) {
      setErrorText(`List devices failed: ${res.error}`);
      return [];
    }
    setOrgName((previous) => res.data.organisation?.name || previous);
    const loaded = res.data.devices || [];
    setDevices(loaded);
    return loaded;
  }, [apiConfig, orgId]);

  const refreshApprovalRequests = useCallback(async () => {
    const res = await listDeviceApprovalRequests(apiConfig, "pending");
    if (res.ok && res.data) setApprovalRequests(res.data.requests || []);
  }, [apiConfig]);

  const refreshDailyScanReports = useCallback(async () => {
    const res = await listDeviceDailyScanReports(apiConfig);
    if (!res.ok || !res.data) return;
    setDailyReportDate(res.data.date || "");
    const map: Record<string, DeviceDailyScanReportItem> = {};
    for (const report of res.data.reports || []) {
      if (report?.device_id) map[report.device_id] = report;
    }
    setDailyReportByDevice(map);
  }, [apiConfig]);

  const refreshCronRuns = useCallback(async (deviceId = cronFilterDeviceId) => {
    setIsListingCronRuns(true);
    const res = await listCronRuns(apiConfig, { deviceId: deviceId || undefined, limit: 500 });
    setIsListingCronRuns(false);
    if (!res.ok || !res.data) {
      setErrorText(`Cron run load failed: ${res.error}`);
      return;
    }
    setCronRuns(res.data.runs || []);
  }, [apiConfig, cronFilterDeviceId]);

  const loadCronRunDetails = useCallback(async (runId: string) => {
    const requestId = (cronRunRequestIds.current[runId] || 0) + 1;
    cronRunRequestIds.current[runId] = requestId;
    setCronRunDetails((previous) => ({
      ...previous,
      [runId]: { status: "loading" },
    }));

    const res = await getCronRunVulnerabilities(apiConfig, runId);
    if (!mountedRef.current || cronRunRequestIds.current[runId] !== requestId) return;
    if (!res.ok || !res.data) {
      setCronRunDetails((previous) => ({
        ...previous,
        [runId]: { status: "error", error: res.error || "Unable to load run findings." },
      }));
      return;
    }
    setCronRunDetails((previous) => ({
      ...previous,
      [runId]: { status: "loaded", data: res.data },
    }));
  }, [apiConfig]);

  const toggleCronRun = useCallback((runId: string) => {
    if (!runId) return;
    if (expandedCronRunIds.has(runId)) {
      setExpandedCronRunIds((previous) => {
        const next = new Set(previous);
        next.delete(runId);
        return next;
      });
      return;
    }

    setExpandedCronRunIds((previous) => new Set(previous).add(runId));
    const detail = cronRunDetails[runId];
    if (!detail || detail.status === "error") {
      void loadCronRunDetails(runId);
    }
  }, [cronRunDetails, expandedCronRunIds, loadCronRunDetails]);

  const refreshAllData = useCallback(async () => {
    if (!baseUrl.trim() || !orgId.trim()) return;
    setErrorText("");
    await Promise.allSettled([
      refreshDevices(false),
      refreshApprovalRequests(),
      refreshDailyScanReports(),
      refreshCronRuns(),
    ]);
  }, [baseUrl, orgId, refreshApprovalRequests, refreshCronRuns, refreshDailyScanReports, refreshDevices]);

  useEffect(() => {
    if (!baseUrl.trim() || !orgId.trim()) return;
    void refreshAllData();
  }, [baseUrl, orgId, refreshAllData]);

  useEffect(() => {
    if (activeTab !== "cron" || !baseUrl.trim() || !orgId.trim()) return;

    let cancelled = false;
    const syncCronRuns = async () => {
      if (cancelled) return;
      await refreshCronRuns(cronFilterDeviceId);
    };

    void syncCronRuns();
    const timer = window.setInterval(() => {
      void syncCronRuns();
    }, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeTab, baseUrl, orgId, cronFilterDeviceId, refreshCronRuns]);

  useEffect(() => {
    if (localDevices.some((device) => device.device_id === cronFilterDeviceId)) return;
    if (cronFilterDeviceId) setCronFilterDeviceId("");
  }, [localDevices, cronFilterDeviceId]);

  const handleApproveDevice = async (deviceId: string) => {
    clearMessages();
    if (!deviceId.trim()) { setErrorText("Device ID is required."); return; }
    setLoading(true);
    const res = await approveDevice(apiConfig, { device_id: deviceId.trim(), approved: true });
    if (!res.ok) { setErrorText(`Approve failed: ${res.error}`); setLoading(false); return; }
    await refreshDevices(false);
    await refreshApprovalRequests();
    setLoading(false);
    setStatusText("Device approved.");
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <h2 className="text-[14px] font-semibold text-foreground">Local Agent Orchestrator</h2>
        <p className="text-[12px] text-muted-foreground">
          Register devices and monitor their daily scans and scheduled cron job results in one place.
        </p>

        <div className="flex items-center gap-2 border-b border-border pb-2">
          {(["devices", "cron"] as const).map((tab) => (
            <button
              key={tab}
              className={`px-6 py-2 text-sm font-medium rounded-md border transition-colors shadow-sm ${activeTab === tab
                ? "border-primary bg-primary/15 text-primary"
                : "border-border/80 bg-background text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                }`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "devices" ? "Registered Devices" : "Cron Job Results"}
            </button>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => setOrgDetailsOpen((value) => !value)}
          >
            {orgDetailsOpen ? "Hide org details" : "Show org details"}
          </Button>
        </div>

        {orgDetailsOpen && (
          <OrgDetailsPanel
            orgs={orgs}
            selectedOrgId={selectedOrgId}
            orgName={orgName}
            orgId={orgId}
            adminKey={adminKey}
            agentToken={agentToken}
            orgsLoading={orgsLoading}
            onSelectOrg={setSelectedOrgId}
          />
        )}

        <div className="rounded-sm border border-border bg-muted/20 px-3 py-2 text-[12px] text-muted-foreground">
          Devices register automatically from the installer/agent. Use the pending approvals list below.
        </div>

        {statusText && (
          <div className="rounded-sm border border-primary/30 bg-primary/10 px-3 py-2 text-[12px] text-foreground">
            {statusText}
          </div>
        )}
        {errorText && (
          <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
            {errorText}
          </div>
        )}

        {approvalRequests.length > 0 && (
          <div className="rounded-sm border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] space-y-2">
            <div className="font-semibold text-foreground">
              Pending Approvals: {approvalRequests.length}
            </div>
            {approvalRequests.slice(0, 8).map((request) => (
              <div
                key={`${request.device_id}-${request.updated_at || request.created_at || ""}`}
                className="flex items-center justify-between gap-2 rounded-sm border border-warning/30 bg-background/80 px-2 py-1"
              >
                <div className="text-foreground/90">
                  {request.device_id} ({request.hostname || "unknown-host"})
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={loading}
                  onClick={() => void handleApproveDevice(request.device_id)}
                >
                  Approve Device
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-foreground">Local Agent Overview</h3>
          <Button
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={async () => {
              clearMessages();
              await refreshAllData();
              setStatusText("Refreshed local agent data.");
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-[12px]">
          {[
            { label: "Registered Devices", value: localDevices.length },
            { label: "Devices Scanned Today", value: scannedTodayCount },
            { label: "Completed Cron Runs", value: completedCronRuns },
            { label: "Failed Cron Runs", value: failedCronRuns },
          ].map(({ label, value }) => (
            <div key={label} className="bg-muted/50 border border-border rounded-sm p-3">
              <div className="text-muted-foreground">{label}</div>
              <div className="text-xl font-semibold text-foreground mt-1">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {activeTab === "devices" ? (
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold text-foreground">Registered Devices</h3>
            <Button
              variant="outline"
              size="sm"
              disabled={loading}
              onClick={async () => {
                clearMessages();
                await refreshAllData();
                setStatusText("Refreshed local agent data.");
              }}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
          {isListingDevices ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              Loading registered devices...
            </div>
          ) : localDevices.length === 0 ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              No registered devices available.
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-auto pr-1">
              {localDevices.map((device) => (
                <DeviceCard
                  key={device.device_id}
                  device={device}
                  report={dailyReportByDevice[device.device_id]}
                  dailyReportDate={dailyReportDate}
                  orgId={orgId}
                  loading={loading}
                  apiConfig={apiConfig}
                  onApprove={handleApproveDevice}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[12px] font-semibold text-foreground">Cron Job Results</h3>
            <div className="flex items-center gap-2">
              <select
                aria-label="Filter cron runs by device"
                className="h-8 rounded-md border border-border bg-background px-2 text-[12px] text-foreground"
                value={cronFilterDeviceId}
                onChange={(event) => setCronFilterDeviceId(event.target.value)}
              >
                <option value="">All registered devices</option>
                {localDevices.filter((device) => device.device_id).map((device) => (
                  <option key={device.device_id} value={device.device_id}>
                    {device.device_id}{device.approved ? "" : " (pending)"}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                size="sm"
                disabled={loading || isListingCronRuns}
                onClick={async () => {
                  clearMessages();
                  await refreshCronRuns();
                  setStatusText("Fetched cron job results.");
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </Button>
            </div>
          </div>

          {isListingCronRuns ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              Loading cron job results...
            </div>
          ) : cronRuns.length === 0 ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              No cron job results available.
            </div>
          ) : (
            <div className="space-y-2 max-h-[32rem] overflow-auto pr-1">
              {cronRuns.map((run) => {
                const device = deviceById.get(run.device_id);
                const normalizedStatus = normalizeStatus(run.status);
                return (
                  <div
                    key={run.run_id}
                    className="rounded-sm border border-border bg-muted/20 p-3 text-[12px]"
                  >
                    <button
                      type="button"
                      className="w-full text-left"
                      onClick={() => toggleCronRun(run.run_id)}
                      disabled={!run.run_id}
                      aria-expanded={expandedCronRunIds.has(run.run_id)}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2 font-medium text-foreground">
                          <ChevronDown className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${expandedCronRunIds.has(run.run_id) ? "rotate-180" : ""
                            }`} />
                          <span className="break-all">
                            {run.device_id}
                            {device?.hostname ? ` (${device.hostname})` : ""}
                          </span>
                        </div>
                        <span className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${statusClass(normalizedStatus)}`}>
                          {run.status || "unknown"}
                        </span>
                      </div>
                      <div className="mt-2 grid gap-1 text-muted-foreground md:grid-cols-4">
                        <div>
                          Task Type: <span className="text-foreground">{run.task_type || "-"}</span>
                        </div>
                        <div>
                          Started: <span className="text-foreground">{formatDate(run.started_at)}</span>
                        </div>
                        <div>
                          Duration: <span className="text-foreground">
                            {formatDuration(run.duration_elapsed, run.status, run.completed_at)}
                          </span>
                        </div>
                        {run.vulnerability_count !== null && run.vulnerability_count !== undefined && (
                          <div>
                            Vulnerabilities: <span className="text-foreground">{run.vulnerability_count}</span>
                          </div>
                        )}
                      </div>
                    </button>

                    {expandedCronRunIds.has(run.run_id) && (
                      <div className="mt-3 rounded-sm border border-border bg-background/70">
                        {!run.run_id ? (
                          <div className="px-3 py-2 text-muted-foreground">
                            File-level detail is not retained for this run.
                          </div>
                        ) : cronRunDetails[run.run_id]?.status === "loading" ? (
                          <div className="px-3 py-2 text-muted-foreground">
                            Loading file-level findings...
                          </div>
                        ) : cronRunDetails[run.run_id]?.status === "error" ? (
                          <div className="px-3 py-2 text-destructive">
                            Unable to load file-level findings: {cronRunDetails[run.run_id]?.error}
                          </div>
                        ) : !cronRunDetails[run.run_id]?.data?.detail_retained ? (
                          <div className="px-3 py-2 text-muted-foreground">
                            File-level detail is not retained for this run.
                          </div>
                        ) : (() => {
                          const detail = cronRunDetails[run.run_id]?.data;
                          const findings = detail?.vulnerabilities || [];
                          const visibleFindings = findings.slice(0, MAX_RENDERED_CRON_FINDINGS);
                          return (
                            <div>
                              {findings.length === 0 ? (
                                <div className="px-3 py-2 text-muted-foreground">
                                  No file-level findings recorded for this run.
                                </div>
                              ) : (
                                <>
                                  <div className="grid grid-cols-3 gap-2 border-b border-border bg-muted/10 px-3 py-2 text-[11px]">
                                    <div>
                                      <div className="text-muted-foreground">Findings</div>
                                      <div className="font-semibold text-foreground">{findings.length}</div>
                                    </div>
                                    <div>
                                      <div className="text-muted-foreground">Exposed Matches</div>
                                      <div className="font-semibold text-foreground">
                                        {detail?.summary.total_exposed_matches ?? 0}
                                      </div>
                                    </div>
                                    <div>
                                      <div className="text-muted-foreground">Max Priority</div>
                                      <div className="font-semibold text-foreground">
                                        {typeof detail?.summary.max_priority_score === "number"
                                          ? `${(detail.summary.max_priority_score * 100).toFixed(0)}%`
                                          : "-"}
                                      </div>
                                    </div>
                                  </div>
                                  <div className="overflow-x-auto">
                                    <table className="w-full text-[11px]">
                                      <thead className="bg-muted">
                                        <tr>
                                          <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">File Path</th>
                                          <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">PII Type</th>
                                          <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Matches</th>
                                          <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Priority</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {visibleFindings.map((finding, index) => (
                                          <tr
                                            key={`${finding.path_or_port || "path"}-${finding.data_type || "type"}-${index}`}
                                            className="border-t border-border hover:bg-muted/20"
                                          >
                                            <td className="max-w-[18rem] break-all px-3 py-1.5 font-mono text-muted-foreground" title={finding.path_or_port || undefined}>
                                              {shortenFindingPath(finding.path_or_port)}
                                            </td>
                                            <td className="px-3 py-1.5 text-foreground">
                                              {finding.data_type || "-"}
                                            </td>
                                            <td className="px-3 py-1.5 text-foreground">
                                              {finding.match_count ?? "-"}
                                            </td>
                                            <td className="px-3 py-1.5">
                                              <span className={`rounded-sm border px-1.5 py-0.5 text-[10px] ${findingPriorityClass(finding.priority_score)}`}>
                                                {typeof finding.priority_score === "number"
                                                  ? `${(finding.priority_score * 100).toFixed(0)}%`
                                                  : "-"}
                                              </span>
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                  {findings.length > visibleFindings.length && (
                                    <div className="border-t border-border px-3 py-2 text-muted-foreground">
                                      Showing the first {visibleFindings.length} of {findings.length} findings.
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}