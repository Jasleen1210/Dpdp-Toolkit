import { useEffect, useState } from "react";
import { useLocation, Link } from "react-router-dom";
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
  awaiting_approval: "bg-warning/10 text-warning",
};

const API =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") 

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

function RequestTable({
  requests,
  onApprove,
}: {
  requests: DSRRequest[];
  onApprove: (id: string) => void;
}) {
  return (
    <div className="bg-card border border-border rounded-sm sovereign-shadow overflow-x-auto fade-right-mask">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="px-4 py-2.5">ID</th>
            <th className="px-4 py-2.5">Type</th>
            <th className="px-4 py-2.5">Subject</th>
            <th className="px-4 py-2.5">Status</th>
            <th className="px-4 py-2.5">SLA</th>
            <th className="px-4 py-2.5">Handler</th>
            <th className="px-4 py-2.5">Created</th>
            <th className="px-4 py-2.5">Action</th>
          </tr>
        </thead>

        <tbody className="divide-y divide-border">
          {requests.map((r) => (
            <tr key={r.id} className="hover:bg-muted/20">
              <td className="px-4 py-2.5 font-mono">{r.id}</td>

              <td className="px-4 py-2.5 uppercase text-[11px]">
                {r.type}
              </td>

              <td className="px-4 py-2.5">{r.subject}</td>

              <td className="px-4 py-2.5">
                <span
                  className={`px-2 py-0.5 text-[11px] rounded-sm ${
                    statusColors[r.status]
                  }`}
                >
                  {r.status.replace("_", " ")}
                </span>
              </td>

              <td className="px-4 py-2.5">{r.sla_remaining}</td>
              <td className="px-4 py-2.5">{r.handler}</td>
              <td className="px-4 py-2.5">{r.created}</td>

              <td className="px-4 py-2.5">
                {r.status === "awaiting_approval" && (
                  <button
                    onClick={() => onApprove(r.id)}
                    className="px-2 py-1 text-[11px] bg-primary text-white rounded-sm"
                  >
                    Approve
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {requests.length === 0 && (
        <div className="p-6 text-center text-muted-foreground">
          No requests found.
        </div>
      )}
    </div>
  );
}

const fetchRequests = async () => {
  const res = await fetch(`${API}/cloud/requests`);
  const data = await res.json();
  return data.requests || [];
};

export default function RequestsPage() {
  const location = useLocation();
  const path = location.pathname;

  const [requests, setRequests] = useState<DSRRequest[]>([]);

  const loadData = async () => {
    const data = await fetchRequests();
    setRequests(data);
  };

  useEffect(() => {
    loadData();

    const interval = setInterval(loadData, 5000); // auto refresh
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (id: string) => {
    await fetch(`${API}/cloud/dpdp/approve/${id}`, {
      method: "POST",
    });
    loadData();
  };

  const filtered =
    path === "/requests/delete"
      ? requests.filter((r) => r.type === "delete")
      : path === "/requests/access"
      ? requests.filter((r) => r.type === "access")
      : path === "/requests/correction"
      ? requests.filter((r) => r.type === "update")
      : requests;

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h1 className="text-lg font-bold">Requests (DSR)</h1>
        <p className="text-[13px] text-muted-foreground">
          Data Subject Request handler
        </p>
      </div>

      <SubtabNav />

      <RequestTable requests={filtered} onApprove={handleApprove} />
    </div>
  );
}