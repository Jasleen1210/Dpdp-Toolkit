import { useEffect, useState } from "react";
import { useLocation, Link } from "react-router-dom";
// import { fetchDSRRequests } from "@/api/mock";
import type { DSRRequest } from "@/api/types";

const subtabs = [
  { label: "All Requests", href: "/requests" },
  { label: "Delete Requests", href: "/requests/delete" },
  { label: "Access Requests", href: "/requests/access" },
  { label: "Correction Requests", href: "/requests/correction" },
  { label: "Workflow Queue", href: "/requests/queue" },
];

const statusColors: Record<string, string> = {
  pending: "bg-warning/10 text-warning",
  in_progress: "bg-primary/10 text-primary",
  completed: "bg-primary/10 text-primary",
  rejected: "bg-destructive/10 text-destructive",
};

const queueItems = [
  { id: "WF-101", request: "DSR-442", step: "Verify Identity", assignee: "auto-system", status: "in_progress", priority: "high" },
  { id: "WF-100", request: "DSR-441", step: "Locate Data", assignee: "dpo@corp.in", status: "pending", priority: "high" },
  { id: "WF-099", request: "DSR-439", step: "Approval Required", assignee: "legal@corp.in", status: "pending", priority: "medium" },
  { id: "WF-098", request: "DSR-437", step: "Execute Deletion", assignee: "auto-system", status: "in_progress", priority: "critical" },
  { id: "WF-097", request: "DSR-435", step: "Send Confirmation", assignee: "auto-system", status: "completed", priority: "low" },
];

function SubtabNav() {
  const location = useLocation();
  return (
    <div className="flex gap-1 border-b border-border overflow-x-auto">
      {subtabs.map((s) => (
        <Link key={s.href} to={s.href} className={`px-3 py-2 text-[12px] font-medium whitespace-nowrap border-b-2 transition-colors ${
          location.pathname === s.href ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
        }`}>{s.label}</Link>
      ))}
    </div>
  );
}

function RequestTable({ requests }: { requests: DSRRequest[] }) {
  return (
    <div className="bg-card border border-border rounded-sm sovereign-shadow overflow-x-auto fade-right-mask">
      <table className="w-full text-[13px]">
        <thead><tr className="border-b border-border bg-muted/30">
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">ID</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Type</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Subject</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Status</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">SLA</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Handler</th>
          <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Created</th>
        </tr></thead>
        <tbody className="divide-y divide-border">
          {requests.map((r) => (
            <tr key={r.id} className="hover:bg-muted/20">
              <td className="px-4 py-2.5 font-mono-data font-medium text-foreground">{r.id}</td>
              <td className="px-4 py-2.5 font-mono-data text-[11px] text-muted-foreground uppercase">{r.type}</td>
              <td className="px-4 py-2.5 font-mono-data text-foreground">{r.subject}</td>
              <td className="px-4 py-2.5"><span className={`px-2 py-0.5 text-[11px] font-medium rounded-sm ${statusColors[r.status]}`}>{r.status.replace("_", " ")}</span></td>
              <td className="px-4 py-2.5 font-mono-data text-muted-foreground">{r.sla_remaining}</td>
              <td className="px-4 py-2.5 text-muted-foreground uppercase text-[11px]">{r.handler}</td>
              <td className="px-4 py-2.5 font-mono-data text-muted-foreground">{r.created}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {requests.length === 0 && <div className="p-6 text-center text-muted-foreground text-[13px]">No requests found.</div>}
    </div>
  );
}

const fetchRequests = async () => {
  const res = await fetch("http://127.0.0.1:8000/requests");
  const data = await res.json();
  return data.requests;
};

export default function RequestsPage() {
  const location = useLocation();
  const path = location.pathname;
  const [requests, setRequests] = useState<DSRRequest[]>([]);
  useEffect(() => {
    fetchRequests().then(setRequests);
  }, []);

  const filtered = path === "/requests/delete" ? requests.filter(r => r.type === "delete")
    : path === "/requests/access" ? requests.filter(r => r.type === "access")
    : path === "/requests/correction" ? requests.filter(r => r.type === "correction")
    : requests;

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground">Requests (DSR)</h1>
        <p className="text-[13px] text-muted-foreground mt-0.5">Data Subject Request handler — Track lifecycle and SLA</p>
      </div>
      <SubtabNav />
      {/* <button
        onClick={async () => {
          await fetch("http://127.0.0.1:8000/dpdp/request", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              type: "DELETE",
              identifier: "rahul@gmail.com"
            }),
          });

          const updated = await fetchRequests();
          setRequests(updated);
        }}
        className="bg-primary text-white px-4 py-2 rounded"
      >
        Test Delete Request
      </button> */}
      {path !== "/requests/queue" ? (
        <RequestTable requests={filtered} />
      ) : (
        <div className="bg-card border border-border rounded-sm sovereign-shadow overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Workflow</th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Request</th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Step</th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Assignee</th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Status</th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">Priority</th>
            </tr></thead>
            <tbody className="divide-y divide-border">
              {queueItems.map((q) => (
                <tr key={q.id} className="hover:bg-muted/20">
                  <td className="px-4 py-2.5 font-mono-data font-medium text-foreground">{q.id}</td>
                  <td className="px-4 py-2.5 font-mono-data text-primary">{q.request}</td>
                  <td className="px-4 py-2.5 text-foreground">{q.step}</td>
                  <td className="px-4 py-2.5 font-mono-data text-muted-foreground">{q.assignee}</td>
                  <td className="px-4 py-2.5"><span className={`px-2 py-0.5 text-[11px] font-medium rounded-sm ${statusColors[q.status]}`}>{q.status.replace("_", " ")}</span></td>
                  <td className="px-4 py-2.5"><span className={`px-2 py-0.5 text-[11px] font-medium rounded-sm uppercase ${
                    q.priority === "critical" ? "bg-destructive/10 text-destructive" :
                    q.priority === "high" ? "bg-warning/10 text-warning" :
                    q.priority === "medium" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                  }`}>{q.priority}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
