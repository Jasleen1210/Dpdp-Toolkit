import React, { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  RefreshCw,
  Plus,
  X,
  Search,
  Filter,
  ArrowUpDown,
  CheckCircle2,
  Clock,
  AlertCircle,
  HardDrive,
  Cloud,
  Layers,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import type { DSRRequest } from "@/api/types";
import type { TaskHistoryItem } from "@/api/localAgent";
import { TaskCard } from "@/components/data-access/local/components/TaskCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getAuthHeaders } from "@/api/auth-headers";
import { useAppSelector, useAppDispatch } from "@/redux/hooks";
import { setCurrentOrg } from "@/redux/authSlice";

const subtabs = [
  { label: "All Requests", href: "/requests" },
  { label: "Delete Requests", href: "/requests/delete" },
  { label: "Access Requests", href: "/requests/access" },
  { label: "Update Requests", href: "/requests/update" },
  { label: "Workflow Queue", href: "/requests/queue" },
];

const API = ((import.meta.env.VITE_API_URL as string | undefined) || "http://127.0.0.1:8010").replace(/\/$/, "");

const statusColors: Record<string, string> = {
  pending: "bg-warning/15 text-warning border-warning/30",
  in_progress: "bg-primary/15 text-primary border-primary/30",
  completed: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  rejected: "bg-destructive/15 text-destructive border-destructive/30",
  awaiting_approval: "bg-warning/15 text-warning border-warning/30",
  error: "bg-destructive/15 text-destructive border-destructive/30",
};

const formatLabel = (value: string) => value.replace(/_/g, " ");

function SubtabNav() {
  const location = useLocation();
  return (
    <div className="flex gap-1 border-b border-border overflow-x-auto pb-0.5">
      {subtabs.map((tab) => (
        <Link
          key={tab.href}
          to={tab.href}
          className={`px-3 py-2 text-[12px] font-medium whitespace-nowrap border-b-2 transition-colors ${location.pathname === tab.href
            ? "border-primary text-primary"
            : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

function getTargetBadge(request: DSRRequest): string {
  const targets = (request.target_sources || []).map((t) => String(t).toLowerCase());
  const sourceTypes = (request.source_types || []).map((s) => String(s).toLowerCase());
  const devices = request.devices || [];

  if (targets.length === 1 && targets[0] === "cloud") return "cloud";
  if (targets.length === 1 && targets[0] === "local") return "local";
  if (targets.length === 1 && targets[0] === "db") return "db";
  if (targets.length > 1 || (targets.includes("cloud") && targets.includes("local"))) return "all";

  if (sourceTypes.includes("cloud_storage") && !sourceTypes.includes("local_device")) return "cloud";
  if (sourceTypes.includes("local_device") && !sourceTypes.includes("cloud_storage")) return "local";
  if (devices.length > 0) return "local";

  return "cloud";
}

interface DetailedTask {
  id?: string;
  task_id: string;
  request_id?: string;
  task_group_id?: string;
  device_id?: string;
  status: string;
  query?: string;
  type?: string;
  paths?: string[];
  created_at?: string;
  expires_at?: string;
  completed_at?: string;
  scanned_files: number;
  matches_count: number;
  pii_types: string[];
  matches: Array<{ type?: string; value?: string; file?: string; location?: string }>;
  status_reason?: string;
  delete_replacements?: Array<{
    file: string;
    original_value: string;
    masked_value: string;
    block_signature: string;
  }>;
}

interface RequestDetailData {
  request: Record<string, unknown>;
  local_tasks: DetailedTask[];
  cloud_results: Array<{
    provider?: string;
    bucket?: string;
    location?: string;
    file?: string;
    action_taken?: string;
    status?: string;
  }>;
  status_message?: string;
  db_results?: Array<{
    source_id?: string;
    display_name?: string;
    status?: string;
    summary?: Record<string, number>;
    findings?: Array<Record<string, unknown>>;
    impacted_locations?: number;
    impacted_rows?: number;
    error?: string;
  }>;
  db_errors?: Array<{ source_id?: string; display_name?: string; error?: string }>;
}

function toTaskHistoryItem(task: DetailedTask): TaskHistoryItem {
  const matches = task.matches || [];
  return {
    id: task.task_id || task.id || "",
    request_id: task.request_id,
    task_group_id: task.task_group_id,
    device_id: task.device_id,
    type: task.type,
    query: task.query,
    paths: task.paths || [],
    status: task.status,
    created_at: task.created_at,
    expires_at: task.expires_at,
    completed_at: task.completed_at,
    scanned_files: task.scanned_files || 0,
    matches_count: task.matches_count ?? matches.length,
    pii_types: task.pii_types || [],
    matches: matches.map((m) => ({
      type: m.type || "",
      value: m.value || "",
      file: m.file || m.location || "",
    })),
    delete_replacements: task.delete_replacements,
  };
}

function RequestCard({
  request,
  expanded,
  onToggle,
  onApprove,
  approving,
  authHeaders,
}: {
  request: DSRRequest;
  expanded: boolean;
  onToggle: () => void;
  onApprove: (id: string) => void;
  approving: boolean;
  authHeaders: Record<string, string>;
}) {
  const isAwaitingApproval = Boolean(request.requires_approval) && request.status === "awaiting_approval";
  const wasApproved = Boolean(request.requires_approval) && !isAwaitingApproval && request.status !== "rejected";
  const targetTag = getTargetBadge(request);
  const [detail, setDetail] = useState<RequestDetailData | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    const fetchDetail = async () => {
      setLoadingDetail(true);
      try {
        const res = await fetch(`${API}/requests/${request.id}`, { headers: authHeaders });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setDetail(data);
        }
      } catch { }
      if (!cancelled) setLoadingDetail(false);
    };
    void fetchDetail();
    return () => {
      cancelled = true;
    };
  }, [expanded, request.id]);

  return (
    <div className="border border-border rounded-sm overflow-hidden bg-card transition-all hover:border-border/80">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-stretch text-left bg-muted/20 hover:bg-muted/40 transition-colors"
      >
        <div className="flex w-9 shrink-0 items-center justify-center border-r border-border bg-background/40 px-1">
          <span className="rotate-180 [writing-mode:vertical-rl] text-[9px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
            {request.type}
          </span>
        </div>
        <div className="flex flex-1 items-start justify-between gap-3 px-3.5 py-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-[13px] text-foreground break-all">
                {request.subject}
              </span>
              <span className="px-2 py-0.5 rounded-sm border text-[10px] uppercase font-mono-data bg-muted text-muted-foreground border-border flex items-center gap-1">
                {targetTag === "cloud" ? (
                  <Cloud className="h-3 w-3" />
                ) : targetTag === "local" ? (
                  <HardDrive className="h-3 w-3" />
                ) : (
                  <Layers className="h-3 w-3" />
                )}
                {targetTag}
              </span>
              <span
                className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${statusColors[request.status] || "bg-muted text-muted-foreground border-border"
                  }`}
              >
                {formatLabel(request.status)}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <span className="font-mono-data">ID: {request.id}</span>
              <span>Submitted: {request.created}</span>
              {request.devices && request.devices.length > 0 && (
                <span>Devices: {request.devices.join(", ")}</span>
              )}
            </div>
          </div>
          <ChevronDown
            className={`h-4 w-4 mt-1 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""
              }`}
          />
        </div>
      </button>

      {expanded && (
        <div className="px-3 py-3 bg-card border-t border-border text-[12px] space-y-3">
          <div className="grid gap-2 md:grid-cols-2">
            <div className="text-muted-foreground">Request ID: <span className="text-foreground">{request.id}</span></div>
            <div className="text-muted-foreground">Type: <span className="text-foreground capitalize">{formatLabel(request.type)}</span></div>
            <div className="text-muted-foreground">Target Scope: <span className="text-foreground uppercase">{targetTag}</span></div>
            <div className="text-muted-foreground">Created: <span className="text-foreground">{request.created}</span></div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Data Subject Identifier</div>
            <div className="text-[12px] text-foreground break-all">{request.subject}</div>
          </div>

          {request.devices && request.devices.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Targeted Local Devices</div>
              <div className="text-[12px] text-foreground break-all">{request.devices.join(", ")}</div>
            </div>
          )}

          {/* Live Local Task & Cloud Results */}
          {loadingDetail && !detail && (
            <div className="text-[11px] text-muted-foreground py-1 flex items-center gap-1.5">
              <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Loading scan updates...
            </div>
          )}

          {detail && detail.local_tasks && detail.local_tasks.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Local Device Scan & Remediation Results</div>
              <div className="space-y-2">
                {detail.local_tasks.map((t) => {
                  const taskId = t.task_id || t.id || "";
                  return (
                    <div key={taskId} className="space-y-1.5">
                      <TaskCard
                        task={toTaskHistoryItem(t)}
                        expanded={Boolean(expandedTaskIds[taskId])}
                        onToggle={() =>
                          setExpandedTaskIds((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
                        }
                      />

                      {t.delete_replacements && t.delete_replacements.length > 0 && (
                        <div className="space-y-1 bg-muted/40 p-2 rounded-sm font-mono text-[10px]">
                          <div className="text-muted-foreground font-semibold uppercase text-[9px]">Redaction Log:</div>
                          {t.delete_replacements.map((r, i) => (
                            <div key={i} className="text-muted-foreground">
                              [REDACTED] <span className="text-foreground">{r.file}</span>: {r.original_value} → {r.masked_value}
                            </div>
                          ))}
                        </div>
                      )}

                      {t.status_reason && (
                        <div className="text-[11px] text-warning">{t.status_reason}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Processing update</div>
            <div className="text-[12px] text-muted-foreground break-all">
              {request.status_message || "Status is being synchronized from the selected sources."}
            </div>
            {request.source_status && Object.keys(request.source_status).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(request.source_status).map(([source, sourceStatus]) => (
                  <span key={source} className="rounded-sm border border-border px-2 py-0.5 uppercase text-[10px]">
                    {source}: {sourceStatus as React.ReactNode}
                  </span>
                ))}
              </div>
            )}
            {request.cloud_error && <div className="mt-1 text-[12px] text-destructive">Cloud: {request.cloud_error}</div>}
          </div>

          {detail && detail.cloud_results && detail.cloud_results.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Cloud Storage Results</div>
              <div className="bg-muted/20 border border-border rounded-sm p-2 font-mono text-[10px] space-y-1 text-muted-foreground">
                {detail.cloud_results.map((c, i) => (
                  <div key={i}>
                    [{c.action_taken ? c.action_taken.toUpperCase() : "SCANNED"}] {c.provider} ({c.bucket}) → <span className="text-foreground">{c.file || c.location}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {detail && detail.db_results && detail.db_results.length > 0 && (() => {
            const results = detail.db_results!;
            const totalRows = results.reduce((sum, r) => sum + (r.impacted_rows || 0), 0);
            const totalLocations = results.reduce(
              (sum, r) => sum + (r.impacted_locations ?? (r.findings ? r.findings.length : 0)),
              0
            );
            const allCompleted = results.every((r) => (r.status || "completed") === "completed");
            return (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Database Results</div>
                {allCompleted && (
                  <div className="rounded-sm border border-success/30 bg-emerald-500/5 px-3 py-2 text-[11px] text-emerald-600 mb-2">
                    Database request completed successfully — {totalRows} row{totalRows === 1 ? "" : "s"} changed across {totalLocations} table{totalLocations === 1 ? "" : "s"}/location{totalLocations === 1 ? "" : "s"}.
                  </div>
                )}
                <div className="bg-muted/20 border border-border rounded-sm p-2 font-mono text-[10px] space-y-1 text-muted-foreground">
                  {results.map((result, index) => (
                    <div key={`${result.source_id || "db"}-${index}`}>
                      [{(result.status || "completed").toUpperCase()}] {result.display_name || result.source_id || "Database source"}
                      {result.impacted_rows !== undefined && ` - ${result.impacted_rows} row(s) changed`}
                      {result.impacted_locations !== undefined && ` in ${result.impacted_locations} table(s)`}
                      {result.summary && ` - ${result.summary.finding_count || 0} findings`}
                      {result.error && <span className="text-destructive"> - {result.error}</span>}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {detail && detail.db_errors && detail.db_errors.length > 0 && (
            <div className="text-[11px] text-destructive">
              Database: {detail.db_errors.map((error) => error.error).filter(Boolean).join("; ")}
            </div>
          )}

          {detail && detail.local_tasks && detail.local_tasks.length > 0 && detail.local_tasks.every((t) => t.status === "completed") && (
            <div className="rounded-sm border border-success/30 bg-emerald-500/5 px-3 py-2 text-[11px] text-emerald-600">
              Request completed successfully with results available for review.
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border">
            <span className="text-muted-foreground">
              Handler: <span className="text-foreground capitalize">{request.handler}</span>
            </span>
            {isAwaitingApproval && (
              <Button
                size="sm"
                disabled={approving}
                onClick={() => onApprove(request.id)}
                className="h-8 text-[12px]"
              >
                {approving ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Approving
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> Approve Request
                  </>
                )}
              </Button>
            )}
            {wasApproved && (
              <span className="inline-flex items-center gap-1.5 rounded-sm border border-success/30 bg-emerald-500/10 px-2.5 py-1.5 text-[12px] text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" /> Approved
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

async function fetchRequests(token: string | null, orgId: string | null): Promise<DSRRequest[]> {
  const headers: Record<string, string> = {};
  if (token && !token.startsWith("guest_")) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (orgId) headers["X-Org-Id"] = orgId;

  try {
    const res = await fetch(`${API}/requests`, { headers });
    if (res.ok) {
      const data = await res.json();
      if (data && Array.isArray(data.requests)) return data.requests;
    }
  } catch (err) {
    console.warn("Primary /requests fetch failed, attempting fallback:", err);
  }

  try {
    const fallback = await fetch(`${API}/cloud/requests`, { headers });
    if (fallback.ok) {
      const data = await fallback.json();
      return Array.isArray(data.requests) ? data.requests : [];
    }
  } catch (err) {
    console.error("All request fetch attempts failed:", err);
  }
  return [];
}

export default function RequestsPage() {
  const location = useLocation();
  const [requests, setRequests] = useState<DSRRequest[]>([]);
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  // Search, Filters & Sorting state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedTarget, setSelectedTarget] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "subject" | "status">("newest");

  // Modal State for New DSR Request
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createType, setCreateType] = useState<"delete" | "access" | "update">("delete");
  const [createIdentifier, setCreateIdentifier] = useState("");
  const [createNewValue, setCreateNewValue] = useState("");
  const [createTarget, setCreateTarget] = useState<"all" | "local" | "cloud" | "db">("all");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const authToken = useAppSelector((state) => state.auth.token);
  const currentOrgId = useAppSelector((state) => state.auth.currentOrgId);
  const organisations = useAppSelector((state) => state.auth.organisations);
  const dispatch = useAppDispatch();
  const authHeaders = useMemo(() => {
    if (!authToken || authToken.startsWith("guest_") || !currentOrgId) return {};
    return getAuthHeaders(authToken, currentOrgId);
  }, [authToken, currentOrgId]);

  const loadData = async (showLoading = false) => {
    if (showLoading) setIsRefreshing(true);
    if (!authToken || authToken.startsWith("guest_") || !currentOrgId) {
      setRequests([]);
      setInitialLoading(false);
      if (showLoading) setIsRefreshing(false);
      return;
    }
    try {
      const data = await fetchRequests(authToken, currentOrgId);
      setRequests(data);
    } catch (err) {
      console.error("Failed to load requests:", err);
    } finally {
      if (showLoading) setIsRefreshing(false);
      setInitialLoading(false);
    }
  };

  useEffect(() => {
    void loadData(true);
    const interval = window.setInterval(() => void loadData(false), 5000);
    return () => window.clearInterval(interval);
  }, [authToken, currentOrgId]);

  const handleApprove = async (id: string) => {
    setApprovingId(id);
    const headers: Record<string, string> = { ...authHeaders, "Content-Type": "application/json" };

    try {
      const res = await fetch(`${API}/requests/${id}/approve`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error("Unified approve failed");
    } catch {
      try {
        await fetch(`${API}/cloud/requests/${id}/approve`, {
          method: "POST",
          headers,
        });
      } catch (e) {
        console.error("All approve attempts failed:", e);
      }
    } finally {
      setApprovingId(null);
      await loadData(true);
    }
  };

  const handleCreateRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createIdentifier.trim()) {
      setCreateError("Identifier (e.g. Phone number or Email) is required");
      return;
    }
    if (createType === "update" && !createNewValue.trim()) {
      setCreateError("New value is required for update requests");
      return;
    }

    setCreateLoading(true);
    setCreateError(null);

    const headers: Record<string, string> = { ...authHeaders, "Content-Type": "application/json" };

    try {
      const payload = {
        type: createType,
        identifier: createIdentifier.trim(),
        new_value: createType === "update" ? createNewValue.trim() : undefined,
        target: createTarget,
        ...(currentOrgId ? { org_id: currentOrgId } : {}),
      };

      const res = await fetch(`${API}/requests`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.error || "Failed to create request");
      }

      setCreateIdentifier("");
      setCreateNewValue("");
      setIsCreateOpen(false);
      await loadData(true);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Error creating request");
    } finally {
      setCreateLoading(false);
    }
  };

  // Subtab filtering based on current URL path
  const currentPath = location.pathname.toLowerCase().replace(/\/$/, "");
  const baseFiltered = useMemo(() => {
    if (currentPath.endsWith("/delete")) {
      return requests.filter((r) => r.type === "delete");
    }
    if (currentPath.endsWith("/access")) {
      return requests.filter((r) => r.type === "access");
    }
    if (currentPath.endsWith("/update") || currentPath.endsWith("/correction")) {
      return requests.filter((r) => r.type === "update");
    }
    if (currentPath.endsWith("/queue")) {
      return requests.filter((r) =>
        ["pending", "in_progress", "awaiting_approval"].includes(r.status)
      );
    }
    return requests;
  }, [requests, currentPath]);

  // Combined Search, Type, Status, Target filter and Sort
  const filteredAndSorted = useMemo(() => {
    let list = [...baseFiltered];

    // Search query match across ID, Subject, Target, Handler, and Devices
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((r) => {
        const idMatch = (r.id || "").toLowerCase().includes(q);
        const subjectMatch = (r.subject || "").toLowerCase().includes(q);
        const handlerMatch = (r.handler || "").toLowerCase().includes(q);
        const typeMatch = (r.type || "").toLowerCase().includes(q);
        const statusMatch = (r.status || "").toLowerCase().includes(q);
        const devicesMatch = (r.devices || []).some((d) => d.toLowerCase().includes(q));
        return idMatch || subjectMatch || handlerMatch || typeMatch || statusMatch || devicesMatch;
      });
    }

    // Type filter
    if (selectedType !== "all") {
      list = list.filter((r) => {
        if (selectedType === "delete") return r.type === "delete";
        if (selectedType === "access") return r.type === "access";
        if (selectedType === "update") return r.type === "update";
        return true;
      });
    }

    // Status filter
    if (selectedStatus !== "all") {
      list = list.filter((r) => {
        if (selectedStatus === "awaiting_approval") {
          return r.status === "awaiting_approval" || (
            r.status === "pending" && r.requires_approval
          );
        }
        return r.status === selectedStatus;
      });
    }

    // Target filter
    if (selectedTarget !== "all") {
      list = list.filter((r) => getTargetBadge(r) === selectedTarget);
    }

    // Helper to extract timestamp for accurate creation time sorting
    const getTimestamp = (req: DSRRequest) => {
      if (req.created_at) {
        const t = new Date(req.created_at).getTime();
        if (!isNaN(t)) return t;
      }
      if (req.created) {
        const t = new Date(req.created).getTime();
        if (!isNaN(t)) return t;
      }
      return 0;
    };

    // Sorting - newest creation timestamp first by default
    list.sort((a, b) => {
      if (sortBy === "newest") {
        const diff = getTimestamp(b) - getTimestamp(a);
        if (diff !== 0) return diff;
        return (b.created || "").localeCompare(a.created || "") || b.id.localeCompare(a.id);
      }
      if (sortBy === "oldest") {
        const diff = getTimestamp(a) - getTimestamp(b);
        if (diff !== 0) return diff;
        return (a.created || "").localeCompare(b.created || "") || a.id.localeCompare(b.id);
      }
      if (sortBy === "subject") {
        return (a.subject || "").localeCompare(b.subject || "");
      }
      if (sortBy === "status") {
        return (a.status || "").localeCompare(b.status || "");
      }
      return 0;
    });

    return list;
  }, [baseFiltered, searchQuery, selectedType, selectedStatus, selectedTarget, sortBy]);

  // Metric stats
  const stats = useMemo(() => {
    const total = requests.length;
    const awaiting = requests.filter(
      (r) => r.status === "awaiting_approval" || r.status === "pending"
    ).length;
    const inProgress = requests.filter((r) => r.status === "in_progress").length;
    const completed = requests.filter((r) => r.status === "completed").length;
    return { total, awaiting, inProgress, completed };
  }, [requests]);

  const hasActiveFilters =
    searchQuery.trim() !== "" ||
    selectedType !== "all" ||
    selectedStatus !== "all" ||
    selectedTarget !== "all";

  const clearFilters = () => {
    setSearchQuery("");
    setSelectedType("all");
    setSelectedStatus("all");
    setSelectedTarget("all");
    setSortBy("newest");
  };

  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-foreground">Requests (DSR)</h1>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Search, filter, approve, and track data subject requests across cloud and local devices.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {organisations && organisations.length > 0 && (
            <select
              value={currentOrgId || ""}
              onChange={(e) => dispatch(setCurrentOrg(e.target.value))}
              className="h-9 rounded-md border border-border bg-background px-3 py-1 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-medium"
            >
              {organisations.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </select>
          )}
          <Button size="sm" onClick={() => setIsCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Create new DSR
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={isRefreshing}
            onClick={() => void loadData(true)}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${isRefreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* Subtab Navigation */}
      <SubtabNav />

      {/* Quick Summary Metric Pills */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-[12px]">
        <div className="bg-card border border-border rounded-sm p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Layers className="h-3.5 w-3.5 text-primary" />
            <span>Total Requests</span>
          </div>
          <span className="font-semibold text-foreground">{stats.total}</span>
        </div>
        <div className="bg-card border border-border rounded-sm p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <AlertCircle className="h-3.5 w-3.5 text-warning" />
            <span>Awaiting Approval</span>
          </div>
          <span className="font-semibold text-warning">{stats.awaiting}</span>
        </div>
        <div className="bg-card border border-border rounded-sm p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock className="h-3.5 w-3.5 text-primary" />
            <span>In Progress</span>
          </div>
          <span className="font-semibold text-foreground">{stats.inProgress}</span>
        </div>
        <div className="bg-card border border-border rounded-sm p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            <span>Completed</span>
          </div>
          <span className="font-semibold text-emerald-500">{stats.completed}</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-card border border-border rounded-sm p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ID, email, phone, subject, device, or handler..."
              className="pl-8 h-8 text-[12px]"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Type Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground hidden sm:inline">Type:</span>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="h-8 rounded-sm border border-border bg-background px-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all">All Types</option>
              <option value="delete">Delete</option>
              <option value="access">Access</option>
              <option value="update">Update</option>
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground hidden sm:inline">Status:</span>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="h-8 rounded-sm border border-border bg-background px-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all">All Statuses</option>
              <option value="awaiting_approval">Awaiting Approval</option>
              <option value="pending">Pending</option>
              <option value="in_progress">In Progress</option>
              <option value="completed">Completed</option>
              <option value="rejected">Rejected</option>
              <option value="error">Error</option>
            </select>
          </div>

          {/* Target Infrastructure Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground hidden sm:inline">Target:</span>
            <select
              value={selectedTarget}
              onChange={(e) => setSelectedTarget(e.target.value)}
              className="h-8 rounded-sm border border-border bg-background px-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all">All Targets</option>
              <option value="cloud">Cloud Storage</option>
              <option value="local">Local Devices</option>
              <option value="db">Database</option>
            </select>
          </div>

          {/* Sort By */}
          <div className="flex items-center gap-1.5">
            <ArrowUpDown className="h-3 w-3 text-muted-foreground hidden sm:inline" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              className="h-8 rounded-sm border border-border bg-background px-2 text-[12px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="subject">Subject (A-Z)</option>
              <option value="status">Status</option>
            </select>
          </div>

          {/* Reset Filters */}
          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="h-8 text-[11px] text-muted-foreground hover:text-foreground px-2"
            >
              <X className="h-3.5 w-3.5 mr-1" /> Reset
            </Button>
          )}
        </div>

        {/* Results summary bar */}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/60">
          <span>
            Showing <strong className="text-foreground font-medium">{filteredAndSorted.length}</strong> of{" "}
            {requests.length} requests
            {hasActiveFilters && " (filtered)"}
          </span>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline">Auto-refreshes every 5s</span>
          </div>
        </div>
      </div>

      {/* Requests Feed / List */}
      <div className="space-y-2.5">
        {initialLoading ? (
          <div className="rounded-sm border border-border bg-card p-10 text-center text-[12px] text-muted-foreground flex flex-col items-center justify-center gap-3">
            <RefreshCw className="h-5 w-5 animate-spin text-primary" />
            <span>Loading user requests and live execution status...</span>
          </div>
        ) : filteredAndSorted.length ? (
          filteredAndSorted.map((request) => (
            <RequestCard
              key={request.id}
              request={request}
              expanded={!!expandedIds[request.id]}
              onToggle={() =>
                setExpandedIds((current) => ({
                  ...current,
                  [request.id]: !current[request.id],
                }))
              }
              onApprove={handleApprove}
              approving={approvingId === request.id}
              authHeaders={authHeaders}
            />
          ))
        ) : (
          <div className="rounded-sm border border-border bg-card p-10 text-center text-[12px] text-muted-foreground space-y-3">
            <div className="flex justify-center">
              <Filter className="h-6 w-6 text-muted-foreground/60" />
            </div>
            <p className="font-medium text-foreground">No matching requests found</p>
            <p className="text-[11px]">
              {hasActiveFilters
                ? "Try adjusting your search criteria or clearing active filters."
                : "No requests have been submitted yet. Create one using the button above."}
            </p>
            {hasActiveFilters ? (
              <Button size="sm" variant="outline" onClick={clearFilters} className="h-7 text-[11px]">
                Clear All Filters
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => void loadData(true)}
                className="h-7 text-[11px]"
              >
                <RefreshCw className="h-3 w-3 mr-1" /> Refresh
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Modal Dialog for Create New DSR */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md bg-card border border-border rounded-sm shadow-lg overflow-hidden">
            <div className="flex items-center justify-between p-3.5 border-b border-border bg-muted/20">
              <h2 className="text-sm font-semibold text-foreground">Create New DSR Request</h2>
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateRequest} className="p-4 space-y-3.5 text-[12px]">
              {createError && (
                <div className="p-2.5 rounded-sm border border-destructive/30 bg-destructive/10 text-destructive text-[11px]">
                  {createError}
                </div>
              )}

              {/* Request Type */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1.5">
                  Request Type
                </label>
                <div className="flex gap-4 items-center bg-muted/20 p-2 rounded-sm border border-border">
                  {(["delete", "access", "update"] as const).map((type) => (
                    <label key={type} className="flex items-center gap-2 capitalize cursor-pointer">
                      <input
                        type="radio"
                        name="createType"
                        value={type}
                        checked={createType === type}
                        onChange={() => setCreateType(type)}
                        className="accent-primary h-3.5 w-3.5"
                      />
                      <span className="text-foreground text-[12px]">{type}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Target Infrastructure */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1.5">
                  Target Infrastructure
                </label>
                <div className="flex flex-col gap-2.5 bg-muted/20 p-2.5 rounded-sm border border-border">
                  {(
                    [
                      { key: "all", label: "All Storage (Cloud + Local + DB)" },
                      { key: "local", label: "Local Files Only" },
                      { key: "cloud", label: "Cloud Storage (AWS/Azure/GCP)" },
                      { key: "db", label: "Database Sources" },
                    ] as const
                  ).map((tgt) => (
                    <label key={tgt.key} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="createTarget"
                        value={tgt.key}
                        checked={createTarget === tgt.key}
                        onChange={() => setCreateTarget(tgt.key)}
                        className="accent-primary h-3.5 w-3.5"
                      />
                      <span className="text-foreground text-[12px]">{tgt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Identifier */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Data Subject Identifier (Phone Number / Email / Name)
                </label>
                <Input
                  value={createIdentifier}
                  onChange={(e) => setCreateIdentifier(e.target.value)}
                  placeholder="e.g. +91 98765 43210 or rahul@gmail.com"
                  className="h-8 text-[12px]"
                />
              </div>

              {/* Replacement value if update */}
              {createType === "update" && (
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                    New Replacement Value
                  </label>
                  <Input
                    value={createNewValue}
                    onChange={(e) => setCreateNewValue(e.target.value)}
                    placeholder="e.g. +91 99999 00000 or newemail@gmail.com"
                    className="h-8 text-[12px]"
                  />
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsCreateOpen(false)}
                  className="h-8 text-[12px]"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={createLoading}
                  className="h-8 text-[12px]"
                >
                  {createLoading ? "Submitting..." : "Create Request"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
