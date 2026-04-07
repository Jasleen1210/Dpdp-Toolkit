import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, RefreshCw } from "lucide-react";
import {
  approveDevice,
  createTask,
  getMyOrganisations,
  getTaskGroupResults,
  listDeviceApprovalRequests,
  listOrganisationDevices,
  listTasks,
  type Device,
  type DeviceApprovalRequestItem,
  type OrganisationInfo,
  type TaskGroupResultResponse,
  type TaskHistoryItem,
} from "../../../api/localAgent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { setOrganisations } from "@/redux/authSlice";

type ActiveTab = "register" | "new-task";

function formatDate(value?: string): string {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "pending") return "bg-warning/15 text-warning border-warning/30";
  if (s === "completed") return "bg-primary/15 text-primary border-primary/30";
  if (s === "expired")
    return "bg-destructive/15 text-destructive border-destructive/30";
  return "bg-muted text-muted-foreground border-border";
}

export default function LocalFilesPanel() {
  const dispatch = useAppDispatch();
  const [activeTab, setActiveTab] = useState<ActiveTab>("register");
  const authOrgs = useAppSelector((state) => state.auth.organisations);
  const authToken = useAppSelector((state) => state.auth.token);
  const authMode = useAppSelector((state) => state.auth.mode);

  const envBaseUrl = (
    (import.meta.env.VITE_API_URL as string | undefined) || ""
  ).trim();

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
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [taskTargetDeviceIds, setTaskTargetDeviceIds] = useState<string[]>([]);

  const [latestTaskGroupId, setLatestTaskGroupId] = useState("");
  const [devices, setDevices] = useState<Device[]>([]);
  const [approvalRequests, setApprovalRequests] = useState<
    DeviceApprovalRequestItem[]
  >([]);
  const [taskResultGroup, setTaskResultGroup] =
    useState<TaskGroupResultResponse | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([]);

  const [expandedTaskIds, setExpandedTaskIds] = useState<
    Record<string, boolean>
  >({});

  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListingDevices, setIsListingDevices] = useState(false);

  const normalizedBaseUrl = useMemo(
    () => baseUrl.replace(/\/$/, ""),
    [baseUrl],
  );

  const apiConfig = useMemo(
    () => ({
      baseUrl: normalizedBaseUrl,
      orgId: orgId.trim(),
      adminKey: adminKey.trim(),
      agentToken: agentToken.trim(),
    }),
    [normalizedBaseUrl, orgId, adminKey, agentToken],
  );

  const pendingTasks = useMemo(
    () => taskHistory.filter((t) => t.status === "pending"),
    [taskHistory],
  );

  const historyTasks = useMemo(
    () => taskHistory.filter((t) => t.status !== "pending"),
    [taskHistory],
  );

  const clearMessages = () => {
    setStatusText("");
    setErrorText("");
  };

  const approvedDevices = useMemo(
    () => devices.filter((d) => d.approved && d.device_id),
    [devices],
  );

  useEffect(() => {
    const approvedSet = new Set(approvedDevices.map((d) => d.device_id));
    setTaskTargetDeviceIds((prev) => prev.filter((id) => approvedSet.has(id)));
  }, [approvedDevices]);

  useEffect(() => {
    if ((authOrgs || []).length > 0) {
      setOrgs(authOrgs);
      return;
    }

    if (authMode === "guest" || !authToken?.trim() || !baseUrl.trim()) {
      setOrgs([]);
      return;
    }

    let active = true;
    const hydrateOrganisations = async () => {
      setOrgsLoading(true);
      const res = await getMyOrganisations(
        {
          baseUrl,
          orgId: "",
          adminKey: "",
          agentToken: "",
        },
        authToken,
      );

      if (!active) return;
      setOrgsLoading(false);

      if (!res.ok || !res.data?.organisations) {
        return;
      }

      const loaded = res.data.organisations;
      setOrgs(loaded);
      dispatch(setOrganisations(loaded));
    };

    void hydrateOrganisations();
    return () => {
      active = false;
    };
  }, [authOrgs, authMode, authToken, baseUrl, dispatch]);

  useEffect(() => {
    const organisations = orgs || [];

    if (!organisations.length) {
      setSelectedOrgId("");
      setOrgId("");
      setOrgName("");
      setAdminKey("");
      setAgentToken("");
      return;
    }

    const selected: OrganisationInfo =
      organisations.find((o) => o.id === selectedOrgId) || organisations[0];

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

    if (!res.ok || !res.data) {
      setErrorText(`List devices failed: ${res.error}`);
      return [];
    }

    setOrgName(res.data.organisation?.name || orgName);

    const loadedDevices = res.data.devices || [];
    setDevices(loadedDevices);
    return loadedDevices;
  };

  const refreshApprovalRequests = async (): Promise<void> => {
    const res = await listDeviceApprovalRequests(apiConfig, "pending");
    if (!res.ok || !res.data) {
      return;
    }
    setApprovalRequests(res.data.requests || []);
  };

  const refreshTaskHistory = async (): Promise<TaskHistoryItem[]> => {
    const res = await listTasks(apiConfig, { limit: 250 });
    if (!res.ok || !res.data) {
      setErrorText(`Task details load failed: ${res.error}`);
      return [];
    }

    const tasks = res.data.tasks || [];
    setTaskHistory(tasks);
    return tasks;
  };

  useEffect(() => {
    const loadDefaults = async () => {
      if (!baseUrl.trim() || !orgId.trim()) {
        return;
      }

      setErrorText("");
      await refreshDevices(false);
      await refreshApprovalRequests();
      await refreshTaskHistory();
    };

    void loadDefaults();
  }, [apiConfig, baseUrl, orgId]);

  const toggleTaskExpand = (taskId: string) => {
    setExpandedTaskIds((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const handleApproveDevice = async (deviceId: string) => {
    clearMessages();
    setLoading(true);

    const targetDeviceId = deviceId.trim();

    if (!targetDeviceId) {
      setLoading(false);
      setErrorText("Device ID is required to approve.");
      return;
    }

    const res = await approveDevice(apiConfig, {
      device_id: targetDeviceId,
      approved: true,
    });

    if (!res.ok) {
      setLoading(false);
      setErrorText(`Approve failed: ${res.error}`);
      return;
    }

    await refreshDevices(false);
    await refreshApprovalRequests();
    setLoading(false);
    setStatusText("Device approved for distributed scans.");
  };

  const handleCreateTask = async () => {
    clearMessages();
    const approvedDeviceIds = approvedDevices.map((d) => d.device_id);

    if (!approvedDeviceIds.length) {
      setErrorText(
        "Create task failed: no approved devices are available in this organisation.",
      );
      return;
    }

    const targetDeviceIds = taskTargetDeviceIds.length
      ? taskTargetDeviceIds
      : approvedDeviceIds;

    setLoading(true);

    const payload = {
      query,
      expires_in_hours: expiresInHours,
      device_ids: targetDeviceIds,
    };

    const res = await createTask(apiConfig, payload);

    if (!res.ok || !res.data) {
      setLoading(false);
      setErrorText(`Create task failed: ${res.error}`);
      return;
    }

    setLatestTaskGroupId(res.data.task_group_id);
    await refreshTaskHistory();

    setLoading(false);
    setStatusText(
      `Task group created: ${res.data.task_group_id} (${res.data.tasks_created} tasks across ${targetDeviceIds.length} device(s))`,
    );
  };

  const handleFetchTaskResults = async () => {
    clearMessages();

    const targetTaskGroupId = latestTaskGroupId.trim();

    if (!targetTaskGroupId) {
      setErrorText("Create a task first to fetch its task group results.");
      return;
    }

    setLoading(true);

    const res = await getTaskGroupResults(apiConfig, targetTaskGroupId);

    setLoading(false);

    if (!res.ok || !res.data) {
      setErrorText(`Fetch results failed: ${res.error}`);
      return;
    }

    setTaskResultGroup(res.data);
    setStatusText(
      `Loaded results for ${res.data.task_group_id}. Tasks: ${res.data.tasks.length}, results: ${res.data.results.length}`,
    );
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <h2 className="text-[14px] font-semibold text-foreground">
          Local Agent Orchestrator
        </h2>
        <p className="text-[12px] text-muted-foreground">
          Register devices, create new tasks, and monitor pending/history in one
          place.
        </p>

        <div className="flex items-center gap-2 border-b border-border pb-2">
          <button
            className={`px-3 py-1.5 text-[12px] rounded-sm border ${
              activeTab === "register"
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("register")}
          >
            Register Devices
          </button>
          <button
            className={`px-3 py-1.5 text-[12px] rounded-sm border ${
              activeTab === "new-task"
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("new-task")}
          >
            Add New Tasks
          </button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => setOrgDetailsOpen((v) => !v)}
          >
            {orgDetailsOpen ? "Hide org details" : "Show org details"}
          </Button>
        </div>

        {orgDetailsOpen ? (
          <div className="grid gap-3 md:grid-cols-2">
            {orgs.length > 1 ? (
              <label className="text-[12px] text-foreground/90 md:col-span-2">
                Select Organisation
                <select
                  className="mt-1 h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                >
                  {orgs.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name} ({org.role || "member"})
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="text-[12px] text-foreground/90 md:col-span-2">
                Organisation
                <Input
                  className="mt-1"
                  value={
                    orgs[0]
                      ? `${orgs[0].name} (${orgs[0].role || "member"})`
                      : ""
                  }
                  readOnly
                  placeholder={
                    orgsLoading
                      ? "Loading organisation..."
                      : "No organisation linked"
                  }
                />
              </label>
            )}

            <label className="text-[12px] text-foreground/90">
              Organisation Name
              <Input
                className="mt-1"
                value={orgName}
                readOnly
                placeholder="-"
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Organisation ID
              <Input
                className="mt-1"
                value={orgId}
                readOnly
                placeholder="Select an organisation"
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Admin Key
              <Input
                className="mt-1"
                type="password"
                value={adminKey}
                readOnly
                placeholder="No admin key synced from login"
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Agent Token
              <Input
                className="mt-1"
                type="password"
                value={agentToken}
                readOnly
                placeholder="No agent token synced from login"
              />
            </label>
          </div>
        ) : null}

        {activeTab === "register" ? (
          <div className="grid gap-3 md:grid-cols-1">
            <div className="rounded-sm border border-border bg-muted/20 px-3 py-2 text-[12px] text-muted-foreground">
              Devices register automatically from the installer/agent. Use the
              pending approvals list below to approve new devices.
            </div>
            <div className="md:col-span-3 flex flex-wrap gap-2">
              {/* Device refresh moved to the Registered Devices panel */}
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-[12px] text-foreground/90 md:col-span-2">
              Search Query
              <Input
                className="mt-1"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="rahul@gmail.com"
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Expires In Hours (max 24)
              <Input
                className="mt-1"
                type="number"
                min={1}
                max={24}
                value={expiresInHours}
                onChange={(e) =>
                  setExpiresInHours(Number(e.target.value || 24))
                }
                placeholder="24"
              />
            </label>

            <div className="text-[12px] text-foreground/90 md:col-span-2">
              Target Devices
              {approvedDevices.length === 0 ? (
                <div className="mt-1 rounded-sm border border-border bg-muted/30 px-3 py-2 text-[12px] text-muted-foreground">
                  No approved devices available. Approve devices first.
                </div>
              ) : (
                <div className="mt-1 space-y-2 rounded-sm border border-border bg-muted/20 p-2">
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        setTaskTargetDeviceIds(
                          approvedDevices.map((d) => d.device_id),
                        )
                      }
                    >
                      Select All Approved
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setTaskTargetDeviceIds([])}
                    >
                      Clear Selection
                    </Button>
                  </div>
                  <div className="space-y-1 max-h-36 overflow-auto pr-1">
                    {approvedDevices.map((d) => (
                      <label
                        key={`task-target-${d.device_id}`}
                        className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-muted"
                      >
                        <input
                          type="checkbox"
                          checked={taskTargetDeviceIds.includes(d.device_id)}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setTaskTargetDeviceIds((prev) =>
                              checked
                                ? [...prev, d.device_id]
                                : prev.filter((id) => id !== d.device_id),
                            );
                          }}
                        />
                        <span className="text-foreground">{d.device_id}</span>
                        <span className="text-muted-foreground">
                          ({d.hostname || "unknown-host"})
                        </span>
                      </label>
                    ))}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {taskTargetDeviceIds.length > 0
                      ? `Selected ${taskTargetDeviceIds.length} device(s)`
                      : "No devices selected. Task will run on all approved devices."}
                  </div>
                </div>
              )}
            </div>

            <div className="md:col-span-2 flex flex-wrap gap-2">
              <Button onClick={handleCreateTask} disabled={loading}>
                Create Task
              </Button>
              <Button
                variant="outline"
                onClick={handleFetchTaskResults}
                disabled={loading}
              >
                Fetch Task Group Results
              </Button>
            </div>
          </div>
        )}

        {statusText ? (
          <div className="rounded-sm border border-primary/30 bg-primary/10 px-3 py-2 text-[12px] text-foreground">
            {statusText}
          </div>
        ) : null}

        {errorText ? (
          <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
            {errorText}
          </div>
        ) : null}

        {approvalRequests.length > 0 ? (
          <div className="rounded-sm border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning space-y-2">
            <div className="font-semibold text-foreground">
              Pending Device Approval Requests: {approvalRequests.length}
            </div>
            <div className="space-y-1">
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
          </div>
        ) : null}
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-foreground">
            Task Details
          </h3>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              clearMessages();
              const loaded = await refreshTaskHistory();
              setStatusText(`Loaded ${loaded.length} tasks.`);
            }}
            disabled={loading}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[12px]">
          <div className="bg-muted/50 border border-border rounded-sm p-3">
            <div className="text-muted-foreground">Pending Tasks</div>
            <div className="text-xl font-semibold text-foreground mt-1">
              {pendingTasks.length}
            </div>
          </div>
          <div className="bg-muted/50 border border-border rounded-sm p-3">
            <div className="text-muted-foreground">History Tasks</div>
            <div className="text-xl font-semibold text-foreground mt-1">
              {historyTasks.length}
            </div>
          </div>
          <div className="bg-muted/50 border border-border rounded-sm p-3">
            <div className="text-muted-foreground">Registered Devices</div>
            <div className="text-xl font-semibold text-foreground mt-1">
              {devices.length}
            </div>
          </div>
        </div>
      </div>

      {activeTab === "register" ? (
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold text-foreground">
              Registered Devices Updates
            </h3>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                clearMessages();
                const loadedDevices = await refreshDevices(true);
                await refreshApprovalRequests();
                setStatusText(
                  `Fetched ${loadedDevices.length} registered devices.`,
                );
              }}
              disabled={loading}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
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
                <div
                  key={device.device_id}
                  className="rounded-sm border border-border bg-muted/20 p-3 text-[12px]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-foreground break-all">
                      {device.device_id}
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${
                        device.approved
                          ? "border-primary/30 bg-primary/15 text-primary"
                          : "border-warning/30 bg-warning/15 text-warning"
                      }`}
                    >
                      {device.approved ? "Approved" : "Pending"}
                    </span>
                  </div>
                  <div className="mt-2 grid gap-1 text-muted-foreground">
                    <div>
                      Hostname:{" "}
                      <span className="text-foreground">
                        {device.hostname || "-"}
                      </span>
                    </div>
                    <div>
                      Version:{" "}
                      <span className="text-foreground">
                        {device.agent_version || "-"}
                      </span>
                    </div>
                    <div>
                      Org:{" "}
                      <span className="text-foreground">
                        {device.organisation_id || orgId}
                      </span>
                    </div>
                    <div>
                      Last Seen:{" "}
                      <span className="text-foreground">
                        {formatDate(device.last_seen)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold text-foreground">
              Task Updates
            </h3>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                clearMessages();
                const loaded = await refreshTaskHistory();
                setStatusText(`Loaded ${loaded.length} tasks.`);
              }}
              disabled={loading}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>
          <div className="space-y-2">
            {taskHistory.length > 0 ? (
              taskHistory.map((task) => {
                const expanded = !!expandedTaskIds[task.id];
                return (
                  <div
                    key={task.id}
                    className="border border-border rounded-sm overflow-hidden"
                  >
                    <button
                      className="w-full flex items-start justify-between gap-3 px-3 py-2 text-left bg-muted/20 hover:bg-muted/40"
                      onClick={() => toggleTaskExpand(task.id)}
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 text-[12px]">
                          <span className="font-medium text-foreground">
                            {task.query || "-"}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${statusClass(task.status)}`}
                          >
                            {task.status}
                          </span>
                        </div>
                        <div className="text-[11px] text-muted-foreground font-mono-data break-all">
                          Task ID: {task.id}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Device: {task.device_id || "-"} | Scanned Files:{" "}
                          {task.scanned_files} | Matches: {task.matches_count}
                        </div>
                      </div>
                      <ChevronDown
                        className={`h-4 w-4 mt-1 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
                      />
                    </button>

                    {expanded ? (
                      <div className="px-3 py-3 bg-card border-t border-border text-[12px] space-y-3">
                        <div className="grid gap-2 md:grid-cols-2">
                          <div className="text-muted-foreground">
                            Created:{" "}
                            <span className="text-foreground">
                              {formatDate(task.created_at)}
                            </span>
                          </div>
                          <div className="text-muted-foreground">
                            Expires:{" "}
                            <span className="text-foreground">
                              {formatDate(task.expires_at)}
                            </span>
                          </div>
                          <div className="text-muted-foreground">
                            Completed:{" "}
                            <span className="text-foreground">
                              {formatDate(task.completed_at)}
                            </span>
                          </div>
                          <div className="text-muted-foreground break-all">
                            Group:{" "}
                            <span className="text-foreground">
                              {task.task_group_id || "-"}
                            </span>
                          </div>
                        </div>

                        <div>
                          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                            Paths
                          </div>
                          <div className="text-[12px] text-foreground font-mono-data break-all">
                            {(task.paths || []).join(", ") || "-"}
                          </div>
                        </div>

                        <div>
                          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                            PII Detected
                          </div>
                          {task.pii_types?.length ? (
                            <div className="flex flex-wrap gap-1">
                              {task.pii_types.map((t) => (
                                <span
                                  key={`${task.id}-${t}`}
                                  className="px-2 py-0.5 text-[10px] bg-primary/15 text-primary border border-primary/30 rounded-sm"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <div className="text-muted-foreground">
                              No PII types recorded.
                            </div>
                          )}
                        </div>

                        <div>
                          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                            Detailed Matches
                          </div>
                          {!task.matches?.length ? (
                            <div className="text-muted-foreground">
                              No matches available.
                            </div>
                          ) : (
                            <div className="max-h-52 overflow-auto rounded-sm border border-border bg-muted/30">
                              <table className="w-full table-fixed text-[11px]">
                                <thead className="sticky top-0 bg-muted">
                                  <tr>
                                    <th className="w-[20%] text-left px-2 py-1 text-muted-foreground">
                                      Type
                                    </th>
                                    <th className="w-[40%] text-left px-2 py-1 text-muted-foreground">
                                      Value
                                    </th>
                                    <th className="w-[40%] text-left px-2 py-1 text-muted-foreground">
                                      File
                                    </th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {task.matches.map((m, idx) => (
                                    <tr
                                      key={`${task.id}-m-${idx}`}
                                      className="border-t border-border"
                                    >
                                      <td className="w-[20%] px-2 py-1 text-foreground break-words">
                                        {m.type}
                                      </td>
                                      <td className="w-[40%] px-2 py-1 text-foreground break-words">
                                        {m.value}
                                      </td>
                                      <td className="w-[40%] px-2 py-1 text-muted-foreground break-words">
                                        {m.file}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })
            ) : (
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
