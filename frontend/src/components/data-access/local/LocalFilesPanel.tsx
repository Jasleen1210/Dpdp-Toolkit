import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, Eye, EyeOff, RefreshCw } from "lucide-react";
import {
  approveDevice,
  createTask,
  getTaskGroupResults,
  listDevices,
  listTasks,
  registerDevice,
  type Device,
  type TaskGroupResultResponse,
  type TaskHistoryItem,
} from "../../../api/localAgent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const DEFAULT_BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.trim() || "";
const DEFAULT_ORG_ID =
  (import.meta.env.VITE_ORG_ID as string | undefined)?.trim() || "";
const DEFAULT_ADMIN_KEY =
  (import.meta.env.VITE_ADMIN_API_KEY as string | undefined)?.trim() || "";
const DEFAULT_AGENT_TOKEN =
  (import.meta.env.VITE_AGENT_TOKEN as string | undefined)?.trim() || "";

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
  const [activeTab, setActiveTab] = useState<ActiveTab>("register");

  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [orgId, setOrgId] = useState(DEFAULT_ORG_ID);
  const [adminKey, setAdminKey] = useState(DEFAULT_ADMIN_KEY);
  const [agentToken, setAgentToken] = useState(DEFAULT_AGENT_TOKEN);

  const [deviceId, setDeviceId] = useState("TEST-LAPTOP-01");
  const [hostname, setHostname] = useState("TEST-LAPTOP-01");
  const [agentVersion, setAgentVersion] = useState("0.1.0");

  const [query, setQuery] = useState("rahul@gmail.com");
  const [pathsInput, setPathsInput] = useState(
    "d:/Coding/DPDP/Dpdp-Toolkit/backend/data",
  );
  const [expiresInHours, setExpiresInHours] = useState(24);

  const [taskGroupId, setTaskGroupId] = useState("");
  const [devices, setDevices] = useState<Device[]>([]);
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
  const [hasLoadedDefaults, setHasLoadedDefaults] = useState(false);
  const [showAdminKey, setShowAdminKey] = useState(false);
  const [showAgentToken, setShowAgentToken] = useState(false);

  const normalizedBaseUrl = useMemo(
    () => baseUrl.replace(/\/$/, "").replace(":8000", ":8001"),
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

  const refreshDevices = async (showPlaceholder = true): Promise<Device[]> => {
    if (showPlaceholder) setIsListingDevices(true);
    const res = await listDevices(apiConfig);
    if (showPlaceholder) setIsListingDevices(false);

    if (!res.ok || !res.data) {
      setErrorText(`List devices failed: ${res.error}`);
      return [];
    }

    const loadedDevices = res.data.devices || [];
    setDevices(loadedDevices);
    return loadedDevices;
  };

  useEffect(() => {
    const loadDefaults = async () => {
      if (!orgId.trim()) {
        return;
      }

      setErrorText("");
      await refreshDevices(false);
      setTaskHistory([]);
      setHasLoadedDefaults(true);
    };

    void loadDefaults();
  }, [apiConfig, orgId, adminKey]);

  const toggleTaskExpand = (taskId: string) => {
    setExpandedTaskIds((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const handleRegisterDevice = async () => {
    clearMessages();
    setLoading(true);

    const res = await registerDevice(apiConfig, {
      device_id: deviceId,
      hostname,
      agent_version: agentVersion,
      organisation_id: orgId,
    });

    if (!res.ok) {
      setLoading(false);
      setErrorText(`Register failed: ${res.error}`);
      return;
    }

    await refreshDevices(false);
    setLoading(false);
    setStatusText(
      "Device registered. If not pre-approved, approve it from admin action.",
    );
  };

  const handleApproveDevice = async () => {
    clearMessages();
    setLoading(true);

    const res = await approveDevice(apiConfig, {
      device_id: deviceId,
      approved: true,
    });

    if (!res.ok) {
      setLoading(false);
      setErrorText(`Approve failed: ${res.error}`);
      return;
    }

    await refreshDevices(false);
    setLoading(false);
    setStatusText("Device approved for distributed scans.");
  };

  const handleListDevices = async () => {
    clearMessages();
    const loadedDevices = await refreshDevices(true);
    setStatusText(`Fetched ${loadedDevices.length} registered devices.`);
  };

  const handleCreateTask = async () => {
    clearMessages();
    setLoading(true);

    const paths = pathsInput
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);

    const res = await createTask(apiConfig, {
      query,
      paths,
      device_ids: [deviceId],
      expires_in_hours: expiresInHours,
    });

    if (!res.ok || !res.data) {
      setLoading(false);
      setErrorText(`Create task failed: ${res.error}`);
      return;
    }

    setTaskGroupId(res.data.task_group_id);

    setLoading(false);
    setStatusText(
      `Task group created: ${res.data.task_group_id} (${res.data.tasks_created} tasks)`,
    );
  };

  const handleFetchTaskResults = async () => {
    clearMessages();

    if (!taskGroupId.trim()) {
      setErrorText("Provide a task group id to fetch results.");
      return;
    }

    setLoading(true);

    const res = await getTaskGroupResults(apiConfig, taskGroupId);

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

        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-[12px] text-foreground/90">
            Backend URL
            <Input
              className="mt-1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </label>

          <label className="text-[12px] text-foreground/90">
            Organisation ID
            <Input
              className="mt-1"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
            />
          </label>

          <label className="text-[12px] text-foreground/90">
            Admin Key
            <div className="relative mt-1">
              <Input
                className="pr-10"
                type={showAdminKey ? "text" : "password"}
                value={adminKey}
                onChange={(e) => setAdminKey(e.target.value)}
              />
              <button
                type="button"
                aria-label={showAdminKey ? "Hide admin key" : "Show admin key"}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setShowAdminKey((v) => !v)}
              >
                {showAdminKey ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </label>

          <label className="text-[12px] text-foreground/90">
            Agent Token
            <div className="relative mt-1">
              <Input
                className="pr-10"
                type={showAgentToken ? "text" : "password"}
                value={agentToken}
                onChange={(e) => setAgentToken(e.target.value)}
              />
              <button
                type="button"
                aria-label={
                  showAgentToken ? "Hide agent token" : "Show agent token"
                }
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setShowAgentToken((v) => !v)}
              >
                {showAgentToken ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </label>
        </div>

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
        </div>

        {activeTab === "register" ? (
          <div className="grid gap-3 md:grid-cols-3">
            <label className="text-[12px] text-foreground/90">
              Device ID
              <Input
                className="mt-1"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Hostname
              <Input
                className="mt-1"
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Agent Version
              <Input
                className="mt-1"
                value={agentVersion}
                onChange={(e) => setAgentVersion(e.target.value)}
              />
            </label>

            <div className="md:col-span-3 flex flex-wrap gap-2">
              <Button onClick={handleRegisterDevice} disabled={loading}>
                Register Device
              </Button>
              <Button
                variant="secondary"
                onClick={handleApproveDevice}
                disabled={loading}
              >
                Approve Device
              </Button>
              <Button
                variant="outline"
                onClick={handleListDevices}
                disabled={loading}
              >
                List Devices
              </Button>
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
              />
            </label>

            <label className="text-[12px] text-foreground/90 md:col-span-2">
              Target Paths (comma separated)
              <Input
                className="mt-1"
                value={pathsInput}
                onChange={(e) => setPathsInput(e.target.value)}
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
              />
            </label>

            <label className="text-[12px] text-foreground/90">
              Task Group ID (results)
              <Input
                className="mt-1"
                value={taskGroupId}
                onChange={(e) => setTaskGroupId(e.target.value)}
              />
            </label>

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
              const res = await listTasks(apiConfig, { limit: 250 });
              if (!res.ok || !res.data) {
                setErrorText(`Task details load failed: ${res.error}`);
                return;
              }
              setTaskHistory(res.data.tasks || []);
              setStatusText(`Loaded ${res.data.tasks?.length || 0} tasks.`);
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

        <div className="space-y-2">
          {taskHistory.length > 0
            ? taskHistory.map((task) => {
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
                              <table className="w-full text-[11px]">
                                <thead className="sticky top-0 bg-muted">
                                  <tr>
                                    <th className="text-left px-2 py-1 text-muted-foreground">
                                      Type
                                    </th>
                                    <th className="text-left px-2 py-1 text-muted-foreground">
                                      Value
                                    </th>
                                    <th className="text-left px-2 py-1 text-muted-foreground">
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
                                      <td className="px-2 py-1 text-foreground">
                                        {m.type}
                                      </td>
                                      <td className="px-2 py-1 text-foreground">
                                        {m.value}
                                      </td>
                                      <td className="px-2 py-1 text-muted-foreground break-all">
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
            : null}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="bg-card border border-border rounded-sm p-3">
          <h3 className="mb-2 text-[12px] font-semibold text-foreground">
            Registered Devices
          </h3>
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

        <div className="bg-card border border-border rounded-sm p-3">
          <h3 className="mb-2 text-[12px] font-semibold text-foreground">
            Selected Task Group Result
          </h3>
          <pre className="max-h-64 overflow-auto rounded-sm border border-border bg-muted p-3 text-[11px] text-foreground">
            {JSON.stringify(taskResultGroup, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
