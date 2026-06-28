import React, { useState } from "react";
import { ChevronDown, ShieldAlert } from "lucide-react";
import type { VulnerabilityItem } from "../../../../api/localAgent";

interface Props {
  vulnerabilities: VulnerabilityItem[];
  summary: {
    total_vulnerabilities?: number;
    total_exposed_matches?: number;
    max_priority_score?: number;
  };
  updatedAt?: string;
  loading?: boolean;
}

function priorityColor(score: number): string {
  if (score >= 0.8) return "text-destructive border-destructive/40 bg-destructive/10";
  if (score >= 0.6) return "text-warning border-warning/40 bg-warning/10";
  return "text-primary border-primary/40 bg-primary/10";
}

function priorityLabel(score: number): string {
  if (score >= 0.8) return "High";
  if (score >= 0.6) return "Medium";
  return "Low";
}

function shortenPath(path: string): string {
  const parts = path.split(/[/\\]/);
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

function formatDate(value?: string): string {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

export function VulnerabilityTable({ vulnerabilities, summary, updatedAt, loading }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="mt-2 rounded-sm border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
        Loading vulnerabilities...
      </div>
    );
  }

  if (!vulnerabilities.length) {
    return (
      <div className="mt-2 rounded-sm border border-border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
        No vulnerabilities recorded for this device.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-sm border border-border overflow-hidden">
      {/* Collapsible header */}
      <button
        className="w-full flex items-center justify-between px-3 py-2 bg-muted/30 hover:bg-muted/50 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-3.5 w-3.5 text-warning" />
          <span className="text-[11px] font-semibold text-foreground">
            Vulnerabilities — {summary.total_vulnerabilities ?? vulnerabilities.length} types,{" "}
            {summary.total_exposed_matches ?? 0} exposed matches
          </span>
        </div>
        <div className="flex items-center gap-2">
          {updatedAt && (
            <span className="text-[10px] text-muted-foreground hidden sm:block">
              Last scan: {formatDate(updatedAt)}
            </span>
          )}
          <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
        </div>
      </button>

      {expanded && (
        <>
          {/* Summary row */}
          <div className="grid grid-cols-3 gap-2 px-3 py-2 bg-muted/10 border-t border-border text-[11px]">
            <div>
              <div className="text-muted-foreground">Total Types</div>
              <div className="font-semibold text-foreground">{summary.total_vulnerabilities ?? vulnerabilities.length}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Exposed Matches</div>
              <div className="font-semibold text-foreground">{summary.total_exposed_matches ?? 0}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Max Risk Score</div>
              <div className="font-semibold text-foreground">
                {((summary.max_priority_score ?? 0) * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-[11px]">
              <thead className="bg-muted sticky top-0">
                <tr>
                  <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-[18%]">Data Type</th>
                  <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-[12%]">Risk</th>
                  <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-[10%]">Matches</th>
                  <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-[12%]">Status</th>
                  <th className="text-left px-3 py-1.5 text-muted-foreground font-medium">File Path</th>
                </tr>
              </thead>
              <tbody>
                {vulnerabilities.map((v, idx) => (
                  <tr
                    key={`${v.data_type}-${v.path_or_port}-${idx}`}
                    className="border-t border-border hover:bg-muted/20"
                  >
                    <td className="px-3 py-1.5">
                      <span className="px-1.5 py-0.5 rounded-sm bg-primary/10 text-primary border border-primary/20 text-[10px] font-mono">
                        {v.data_type}
                      </span>
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={`px-1.5 py-0.5 rounded-sm border text-[10px] ${priorityColor(v.priority_score)}`}>
                        {priorityLabel(v.priority_score)} {(v.priority_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-foreground font-medium">{v.match_count}</td>
                    <td className="px-3 py-1.5">
                      <span className={`px-1.5 py-0.5 rounded-sm border text-[10px] ${
                        v.status === "unresolved"
                          ? "bg-destructive/10 text-destructive border-destructive/30"
                          : "bg-primary/10 text-primary border-primary/30"
                      }`}>
                        {v.status}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground font-mono break-all">
                      <span title={v.path_or_port}>{shortenPath(v.path_or_port)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}