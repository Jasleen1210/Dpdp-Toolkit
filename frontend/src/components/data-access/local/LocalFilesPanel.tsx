import React, { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  approveDevice,
  createRemediationTask,
  CreateTaskRequest,
  listDeviceDailyScanReports,
  getMyOrganisations,
  getTaskGroupResults,
  listDeviceApprovalRequests,
  listOrganisationDevices,
  listTasks,
  type Device,
  type DeviceDailyScanReportItem,
  type DeviceApprovalRequestItem,
  type OrganisationInfo,
  type TaskGroupResultResponse,
  type TaskHistoryItem,
} from "../../../api/localAgent";
import { Button } from "@/components/ui/button";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { setOrganisations } from "@/redux/authSlice";
import { DeviceCard } from "./components/DeviceCard";
import { TaskCard } from "./components/TaskCard";
import { OrgDetailsPanel } from "./components/OrgDetailsPanel";
import { TaskForm } from "./components/TaskForm";

type ActiveTab = "register" | "new-task";

export default function LocalFilesPanel() {
  const dispatch = useAppDispatch();
  const [activeTab, setActiveTab] = useState<ActiveTab>("register");
  const authOrgs = useAppSelector((s) => s.auth.organisations);
  const authToken = useAppSelector((s) => s.auth.token);
  const authMode = useAppSelector((s) => s.auth.mode);

  const envBaseUrl = ((import.meta.env.VITE_API_URL as string | undefined) || "").trim();
  const [baseUrl] = useState(envBaseUrl);

  const [orgId, setOrgId] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [agentToken, setAgentToken] = useState("");
  const [orgName, setOrgName] = useState("");
  const [orgs, setOrgs] = useState<OrganisationInfo[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [orgDetailsOpen, setOrgDetailsOpen] = useState(false);
  const [orgsLoading, setOrgsLoading] = useState(false);

  const [query, setQuery] = useState("rahul@gmail.com");
  const [newValue, setNewValue] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [actionType, setActionType] = useState<"access" | "update" | "delete">("access");
  const [taskTargetDeviceIds, setTaskTargetDeviceIds] = useState<string[]>([]);
  const [latestTaskGroupId, setLatestTaskGroupId] = useState("");

  const [devices, setDevices] = useState<Device[]>([]);
  const [dailyReportDate, setDailyReportDate] = useState("");
  const [dailyReportByDevice, setDailyReportByDevice] = useState<Record<string, DeviceDailyScanReportItem>>({});
  const [approvalRequests, setApprovalRequests] = useState<DeviceApprovalRequestItem[]>([]);
  const [taskResultGroup, setTaskResultGroup] = useState<TaskGroupResultResponse | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([]);
  const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({});

  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListingDevices, setIsListingDevices] = useState(false);

  const normalizedBaseUrl = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);
  const apiConfig = useMemo(() => ({
    baseUrl: normalizedBaseUrl,
    orgId: orgId.trim(),
    adminKey: adminKey.trim(),
    agentToken: agentToken.trim(),
  }), [normalizedBaseUrl, orgId, adminKey, agentToken]);

  const pendingTasks = useMemo(() => taskHistory.filter((t) => t.status === "pending"), [taskHistory]);
  const historyTasks = useMemo(() => taskHistory.filter((t) => t.status !== "pending"), [taskHistory]);
  const approvedDevices = useMemo(() => devices.filter((d) => d.approved && d.device_id), [devices]);

  const clearMessages = () => { setStatusText(""); setErrorText(""); };

  useEffect(() => {
    const approvedSet = new Set(approvedDevices.map((d) => d.device_id));
    setTaskTargetDeviceIds((prev) => prev.filter((id) => approvedSet.has(id)));
  }, [approvedDevices]);

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

  const refreshDevices = async (showPlaceholder = true): Promise<Device[]> => {
    if (showPlaceholder) setIsListingDevices(true);
    const res = await listOrganisationDevices(apiConfig, orgId);
    if (showPlaceholder) setIsListingDevices(false);
    if (!res.ok || !res.data) { setErrorText(`List devices failed: ${res.error}`); return []; }
    setOrgName(res.data.organisation?.name || orgName);
    const loaded = res.data.devices || [];
    setDevices(loaded);
    return loaded;
  };

  const refreshApprovalRequests = async () => {
    const res = await listDeviceApprovalRequests(apiConfig, "pending");
    if (res.ok && res.data) setApprovalRequests(res.data.requests || []);
  };

  const refreshDailyScanReports = async () => {
    const res = await listDeviceDailyScanReports(apiConfig);
    if (!res.ok || !res.data) return;
    setDailyReportDate(res.data.date || "");
    const map: Record<string, DeviceDailyScanReportItem> = {};
    for (const r of res.data.reports || []) { if (r?.device_id) map[r.device_id] = r; }
    setDailyReportByDevice(map);
  };

  const refreshTaskHistory = async (): Promise<TaskHistoryItem[]> => {
    const res = await listTasks(apiConfig, { limit: 250 });
    if (!res.ok || !res.data) { setErrorText(`Task load failed: ${res.error}`); return []; }
    const tasks = res.data.tasks || [];
    setTaskHistory(tasks);
    return tasks;
  };

  useEffect(() => {
    if (!baseUrl.trim() || !orgId.trim()) return;
    setErrorText("");
    void refreshDevices(false);
    void refreshApprovalRequests();
    void refreshDailyScanReports();
    void refreshTaskHistory();
  }, [apiConfig, baseUrl, orgId]);

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

  const handleCreateTask = async () => {
    clearMessages();
    const ids = approvedDevices.map((d) => d.device_id);
    if (!ids.length) { setErrorText("No approved devices available."); return; }
    const targets = taskTargetDeviceIds.length ? taskTargetDeviceIds : ids;
    setLoading(true);

    let ok = 0;
    const errs: string[] = [];
    for (const deviceId of targets) {
      const payload: CreateTaskRequest = {
        action_type: actionType,
        target_value: query,
        device_id: deviceId,
        ...(actionType === "update" && { new_value: newValue }),
      };
      const res = await createRemediationTask(apiConfig, payload);
      if (res.ok && res.data) ok++;
      else errs.push(`${deviceId}: ${res.error || "Unknown error"}`);
    }

    await refreshTaskHistory();
    setLoading(false);
    if (errs.length) setErrorText(`Failed on some devices:\n${errs.join("\n")}`);
    if (ok > 0) setStatusText(`Created ${ok} task(s) across ${targets.length} device(s).`);
  };

  const handleFetchTaskResults = async () => {
    clearMessages();
    if (!latestTaskGroupId.trim()) { setErrorText("Create a task first."); return; }
    setLoading(true);
    const res = await getTaskGroupResults(apiConfig, latestTaskGroupId.trim());
    setLoading(false);
    if (!res.ok || !res.data) { setErrorText(`Fetch failed: ${res.error}`); return; }
    setTaskResultGroup(res.data);
    setStatusText(`Loaded ${res.data.tasks.length} tasks, ${res.data.results.length} results.`);
  };

  return (
    <div className="space-y-4">
      {/* Header + Tabs */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <h2 className="text-[14px] font-semibold text-foreground">Local Agent Orchestrator</h2>
        <p className="text-[12px] text-muted-foreground">
          Register devices, create new tasks, and monitor pending/history in one place.
        </p>

        <div className="flex items-center gap-2 border-b border-border pb-2">
          {(["register", "new-task"] as const).map((tab) => (
            <button key={tab}
              className={`px-3 py-1.5 text-[12px] rounded-sm border ${
                activeTab === tab
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "register" ? "Register Devices" : "Add New Tasks"}
            </button>
          ))}
          <Button type="button" variant="outline" size="sm" className="ml-auto"
            onClick={() => setOrgDetailsOpen((v) => !v)}>
            {orgDetailsOpen ? "Hide org details" : "Show org details"}
          </Button>
        </div>

        {orgDetailsOpen && (
          <OrgDetailsPanel
            orgs={orgs} selectedOrgId={selectedOrgId} orgName={orgName}
            orgId={orgId} adminKey={adminKey} agentToken={agentToken}
            orgsLoading={orgsLoading} onSelectOrg={setSelectedOrgId}
          />
        )}

        {activeTab === "register" ? (
          <div className="rounded-sm border border-border bg-muted/20 px-3 py-2 text-[12px] text-muted-foreground">
            Devices register automatically from the installer/agent. Use the pending approvals list below.
          </div>
        ) : (
          <TaskForm
            actionType={actionType} query={query} newValue={newValue}
            expiresInHours={expiresInHours} approvedDevices={approvedDevices}
            taskTargetDeviceIds={taskTargetDeviceIds} loading={loading}
            onActionTypeChange={setActionType} onQueryChange={setQuery}
            onNewValueChange={setNewValue} onExpiresChange={setExpiresInHours}
            onSelectAll={() => setTaskTargetDeviceIds(approvedDevices.map((d) => d.device_id))}
            onClearSelection={() => setTaskTargetDeviceIds([])}
            onToggleDevice={(id, checked) =>
              setTaskTargetDeviceIds((prev) => checked ? [...prev, id] : prev.filter((x) => x !== id))
            }
            onCreateTask={handleCreateTask}
            onFetchResults={handleFetchTaskResults}
          />
        )}

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
            {approvalRequests.slice(0, 8).map((r) => (
              <div key={`${r.device_id}-${r.updated_at || r.created_at || ""}`}
                className="flex items-center justify-between gap-2 rounded-sm border border-warning/30 bg-background/80 px-2 py-1">
                <div className="text-foreground/90">{r.device_id} ({r.hostname || "unknown-host"})</div>
                <Button size="sm" variant="secondary" disabled={loading}
                  onClick={() => void handleApproveDevice(r.device_id)}>
                  Approve Device
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Stats bar */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-foreground">Task Details</h3>
          <Button variant="outline" size="sm" disabled={loading}
            onClick={async () => { clearMessages(); const t = await refreshTaskHistory(); setStatusText(`Loaded ${t.length} tasks.`); }}>
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[12px]">
          {[
            { label: "Pending Tasks", value: pendingTasks.length },
            { label: "History Tasks", value: historyTasks.length },
            { label: "Registered Devices", value: devices.length },
          ].map(({ label, value }) => (
            <div key={label} className="bg-muted/50 border border-border rounded-sm p-3">
              <div className="text-muted-foreground">{label}</div>
              <div className="text-xl font-semibold text-foreground mt-1">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom panel — devices or tasks depending on tab */}
      {activeTab === "register" ? (
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold text-foreground">Registered Devices</h3>
            <Button variant="outline" size="sm" disabled={loading}
              onClick={async () => {
                clearMessages();
                const d = await refreshDevices(true);
                await refreshApprovalRequests();
                await refreshDailyScanReports();
                setStatusText(`Fetched ${d.length} devices.`);
              }}>
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
          {isListingDevices ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              Loading registered devices...
            </div>
          ) : devices.length === 0 ? (
            <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
              No registered devices available.
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-auto pr-1">
              {devices.map((device) => (
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
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold text-foreground">Task Updates</h3>
            <Button variant="outline" size="sm" disabled={loading}
              onClick={async () => { clearMessages(); const t = await refreshTaskHistory(); setStatusText(`Loaded ${t.length} tasks.`); }}>
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
          <div className="space-y-2">
            {taskHistory.length > 0 ? taskHistory.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                expanded={!!expandedTaskIds[task.id]}
                onToggle={() => setExpandedTaskIds((prev) => ({ ...prev, [task.id]: !prev[task.id] }))}
              />
            )) : (
              <div className="rounded-sm border border-border bg-muted/30 p-3 text-[12px] text-muted-foreground">
                No task updates available.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}