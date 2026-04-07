import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAppSelector } from "@/redux/hooks";
import { Loader2 } from "lucide-react";

type Organisation = {
  id: string;
  name: string;
  role?: string;
  invite_code?: string;
  device_enrollment_code?: string;
  agent_token?: string;
  admin_api_key?: string;
};

type ApiResponse<T> = {
  detail?: string;
} & T;

const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) || ""
).replace(/\/$/, "");

async function parseJson<T>(res: Response): Promise<ApiResponse<T>> {
  const text = await res.text();
  if (!text) return {} as ApiResponse<T>;
  try {
    return JSON.parse(text) as ApiResponse<T>;
  } catch {
    return { detail: text } as ApiResponse<T>;
  }
}

export default function ProfilePage() {
  const token = useAppSelector((state) => state.auth.token);
  const user = useAppSelector((state) => state.auth.user);

  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [createOrgName, setCreateOrgName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const selectedOrg = useMemo(
    () => orgs.find((o) => o.id === selectedOrgId) || orgs[0] || null,
    [orgs, selectedOrgId],
  );

  const authHeaders = useMemo(
    () => ({
      "Content-Type": "application/json",
      Authorization: `Bearer ${token || ""}`,
    }),
    [token],
  );

  const loadOrgs = async () => {
    if (!token || !API_BASE) return;
    setLoading(true);
    setError("");
    const res = await fetch(`${API_BASE}/auth/organisations/mine`, {
      method: "GET",
      headers: authHeaders,
    });
    const data = await parseJson<{ organisations?: Organisation[] }>(res);
    setLoading(false);

    if (!res.ok) {
      setError(data.detail || "Failed to load organisations");
      return;
    }

    const organisations = data.organisations || [];
    setOrgs(organisations);
    if (!selectedOrgId && organisations.length > 0) {
      setSelectedOrgId(organisations[0].id);
    }
  };

  useEffect(() => {
    void loadOrgs();
  }, [token]);

  const handleCreateOrg = async () => {
    if (!createOrgName.trim()) {
      setError("Organisation name is required");
      return;
    }
    setLoading(true);
    setError("");
    setStatus("");

    const res = await fetch(`${API_BASE}/auth/organisations/create`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ name: createOrgName.trim() }),
    });
    const data = await parseJson<{ organisation?: Organisation }>(res);
    setLoading(false);

    if (!res.ok) {
      setError(data.detail || "Create organisation failed");
      return;
    }

    setCreateOrgName("");
    setStatus("Organisation created.");
    await loadOrgs();
  };

  const handleJoinOrg = async () => {
    if (!joinCode.trim()) {
      setError("Invite code is required");
      return;
    }

    setLoading(true);
    setError("");
    setStatus("");

    const res = await fetch(`${API_BASE}/auth/organisations/join`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({ invite_code: joinCode.trim() }),
    });
    const data = await parseJson<{ organisation?: Organisation }>(res);
    setLoading(false);

    if (!res.ok) {
      setError(data.detail || "Join organisation failed");
      return;
    }

    setJoinCode("");
    setStatus("Joined organisation. Invite code rotated.");
    await loadOrgs();
  };

  const handleRotateInviteCode = async () => {
    if (!selectedOrg?.id) {
      setError("Select an organisation first");
      return;
    }

    setLoading(true);
    setError("");
    setStatus("");

    const res = await fetch(
      `${API_BASE}/auth/organisations/rotate-invite-code`,
      {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ organisation_id: selectedOrg.id }),
      },
    );
    const data = await parseJson<{ invite_code?: string }>(res);
    setLoading(false);

    if (!res.ok) {
      setError(data.detail || "Rotate invite code failed");
      return;
    }

    setStatus("Invite code rotated.");
    await loadOrgs();
  };

  const handleDownloadInstaller = async () => {
    if (!selectedOrg?.id) {
      setError("Select an organisation first");
      return;
    }

    setLoading(true);
    setError("");
    setStatus("");

    const res = await fetch(
      `${API_BASE}/auth/organisations/${encodeURIComponent(selectedOrg.id)}/installer`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token || ""}`,
        },
      },
    );

    if (!res.ok) {
      const data = await parseJson<Record<string, never>>(res);
      setLoading(false);
      setError(data.detail || "Installer download failed");
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `dpdp-agent-${selectedOrg.id}.zip`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);

    setLoading(false);
    setStatus("Installer package downloaded.");
  };

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Profile</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your organisation membership and invite access codes.
        </p>
      </div>

      <div className="rounded-sm border border-border bg-card p-4 space-y-2">
        <div className="text-sm font-medium text-foreground">User</div>
        <div className="text-sm text-muted-foreground">
          Name: {user?.name || "-"}
        </div>
        <div className="text-sm text-muted-foreground">
          Email: {user?.email || "-"}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-sm border border-border bg-card p-4 space-y-3">
          <h2 className="text-sm font-semibold text-foreground">
            Create Organisation
          </h2>
          <Input
            value={createOrgName}
            onChange={(e) => setCreateOrgName(e.target.value)}
            placeholder="Acme Data Pvt Ltd"
          />
          <Button onClick={() => void handleCreateOrg()} disabled={loading}>
            Create Organisation
          </Button>
        </div>

        <div className="rounded-sm border border-border bg-card p-4 space-y-3">
          <h2 className="text-sm font-semibold text-foreground">
            Join Organisation
          </h2>
          <Input
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            placeholder="JOIN-AB12CD34"
          />
          <Button
            variant="secondary"
            onClick={() => void handleJoinOrg()}
            disabled={loading}
          >
            Join with Invite Code
          </Button>
        </div>
      </div>

      <div className="rounded-sm border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-foreground">
            Organisation Details
          </h2>
          <Button
            variant="outline"
            onClick={() => void loadOrgs()}
            disabled={loading}
          >
            Refresh
          </Button>
        </div>

        {orgs.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No organisations yet.
          </div>
        ) : (
          <>
            <label
              htmlFor="org-selector"
              className="text-xs text-muted-foreground"
            >
              Select organisation
            </label>
            <select
              id="org-selector"
              className="w-full h-10 rounded-sm border border-border bg-background px-3 text-sm"
              value={selectedOrg?.id || ""}
              onChange={(e) => setSelectedOrgId(e.target.value)}
            >
              {orgs.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name} ({org.role || "member"})
                </option>
              ))}
            </select>

            {selectedOrg ? (
              <div className="grid gap-2 text-sm">
                <div className="text-muted-foreground">
                  Organisation ID:{" "}
                  <span className="text-foreground break-all">
                    {selectedOrg.id}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  Role:{" "}
                  <span className="text-foreground">
                    {selectedOrg.role || "member"}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  Invite Code (one-time style):{" "}
                  <span className="text-foreground">
                    {selectedOrg.invite_code || "-"}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  Device Enrollment Code:{" "}
                  <span className="text-foreground">
                    {selectedOrg.device_enrollment_code || "-"}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  Admin API Key:{" "}
                  <span className="text-foreground">
                    {selectedOrg.admin_api_key ? "********" : "-"}
                  </span>
                </div>
                <div className="text-muted-foreground">
                  Agent Token:{" "}
                  <span className="text-foreground">
                    {selectedOrg.agent_token ? "********" : "-"}
                  </span>
                </div>
              </div>
            ) : null}

            <div>
              <Button
                variant="outline"
                onClick={() => void handleRotateInviteCode()}
                disabled={loading || !selectedOrg}
              >
                Generate New Invite Code
              </Button>
            </div>
            <div>
              <Button
                onClick={() => void handleDownloadInstaller()}
                disabled={loading || !selectedOrg}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Downloading...
                  </>
                ) : (
                  "Download Installer Package"
                )}
              </Button>
            </div>
          </>
        )}
      </div>

      {status ? (
        <div className="rounded-sm border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-foreground">
          {status}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  );
}
