import React from "react";
import { ChevronDown } from "lucide-react";
import type { TaskHistoryItem } from "../../../../api/localAgent";

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
  if (s === "expired") return "bg-destructive/15 text-destructive border-destructive/30";
  return "bg-muted text-muted-foreground border-border";
}

interface Props {
  task: TaskHistoryItem;
  expanded: boolean;
  onToggle: () => void;
}

export function TaskCard({ task, expanded, onToggle }: Props) {
  return (
    <div className="border border-border rounded-sm overflow-hidden">
      <button
        className="w-full flex items-start justify-between gap-3 px-3 py-2 text-left bg-muted/20 hover:bg-muted/40"
        onClick={onToggle}
      >
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[12px]">
            <span className="font-medium text-foreground">{task.query || "-"}</span>
            <span className={`px-2 py-0.5 rounded-sm border text-[10px] uppercase ${statusClass(task.status)}`}>
              {task.status}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground break-all">Task ID: {task.id}</div>
          <div className="text-[11px] text-muted-foreground">
            Device: {task.device_id || "-"} | Scanned Files: {task.scanned_files} | Matches: {task.matches_count}
          </div>
        </div>
        <ChevronDown className={`h-4 w-4 mt-1 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="px-3 py-3 bg-card border-t border-border text-[12px] space-y-3">
          <div className="grid gap-2 md:grid-cols-2">
            <div className="text-muted-foreground">Created: <span className="text-foreground">{formatDate(task.created_at)}</span></div>
            <div className="text-muted-foreground">Expires: <span className="text-foreground">{formatDate(task.expires_at)}</span></div>
            <div className="text-muted-foreground">Completed: <span className="text-foreground">{formatDate(task.completed_at)}</span></div>
            <div className="text-muted-foreground break-all">Group: <span className="text-foreground">{task.task_group_id || "-"}</span></div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Paths</div>
            <div className="text-[12px] text-foreground break-all">{(task.paths || []).join(", ") || "-"}</div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">PII Detected</div>
            {task.pii_types?.length ? (
              <div className="flex flex-wrap gap-1">
                {task.pii_types.map((t) => (
                  <span key={`${task.id}-${t}`}
                    className="px-2 py-0.5 text-[10px] bg-primary/15 text-primary border border-primary/30 rounded-sm">
                    {t}
                  </span>
                ))}
              </div>
            ) : (
              <div className="text-muted-foreground">No PII types recorded.</div>
            )}
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Detailed Matches</div>
            {!task.matches?.length ? (
              <div className="text-muted-foreground">No matches available.</div>
            ) : (
              <div className="max-h-52 overflow-auto rounded-sm border border-border bg-muted/30">
                <table className="w-full table-fixed text-[11px]">
                  <thead className="sticky top-0 bg-muted">
                    <tr>
                      <th className="w-[20%] text-left px-2 py-1 text-muted-foreground">Type</th>
                      <th className="w-[40%] text-left px-2 py-1 text-muted-foreground">Value</th>
                      <th className="w-[40%] text-left px-2 py-1 text-muted-foreground">File</th>
                    </tr>
                  </thead>
                  <tbody>
                    {task.matches.map((m, idx) => (
                      <tr key={`${task.id}-m-${idx}`} className="border-t border-border">
                        <td className="w-[20%] px-2 py-1 text-foreground break-words">{m.type}</td>
                        <td className="w-[40%] px-2 py-1 text-foreground break-words">{m.value}</td>
                        <td className="w-[40%] px-2 py-1 text-muted-foreground break-words">{m.file}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}