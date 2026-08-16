import React, { useEffect, useState } from "react";
import {
  Cloud,
  Plus,
  RefreshCw,
  X,
  CheckCircle2,
  Lock,
  ExternalLink,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const API = ((import.meta.env.VITE_API_URL as string | undefined) || "http://127.0.0.1:8010").replace(/\/$/, "");

interface CloudObject {
  id: number | string;
  provider: string;
  bucket: string;
  region: string;
  objects: number;
  scanned: boolean;
  pii_found: number;
  location?: string;
  file?: string;
}

interface ConnectedSource {
  id: string;
  provider: string;
  bucket: string;
  region: string;
  auth_method?: string;
  role_arn?: string;
  service_account_email?: string;
  status: string;
  approved: boolean;
  updated_at?: string;
}

export default function CloudPanel() {
  const [loading, setLoading] = useState(false);
  const [cloudData, setCloudData] = useState<CloudObject[]>([]);
  const [sources, setSources] = useState<ConnectedSource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Connect Modal State
  const [isConnectOpen, setIsConnectOpen] = useState(false);
  const [provider, setProvider] = useState<"AWS S3" | "Azure Blob Storage" | "GCP Cloud Storage">("AWS S3");
  const [bucketName, setBucketName] = useState("");
  const [region, setRegion] = useState("ap-south-1 (Mumbai)");
  const [authMethod, setAuthMethod] = useState<"role_arn" | "access_keys" | "service_account" | "connection_string">("role_arn");
  const [roleArn, setRoleArn] = useState("");
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [serviceAccountEmail, setServiceAccountEmail] = useState("");
  const [connectionString, setConnectionString] = useState("");
  const [connectLoading, setConnectLoading] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connectSuccess, setConnectSuccess] = useState<string | null>(null);

  const fetchSources = async () => {
    try {
      const res = await fetch(`${API}/cloud/sources`);
      if (res.ok) {
        const data = await res.json();
        if (data.sources) setSources(data.sources);
      }
    } catch {}
  };

  const fetchExistingResults = async () => {
    try {
      const res = await fetch(`${API}/cloud/results`);
      if (res.ok) {
        const data = await res.json();
        if (data.results && data.results.length > 0) {
          const formatted = data.results.map((file: any, index: number) => ({
            id: index,
            provider: file.provider || "Cloud Storage",
            bucket: `${file.bucket || "bucket"}/${file.object_key || file.file || ""}`,
            region: file.region || "global",
            objects: 1,
            scanned: true,
            pii_found: file.pii_instance_count ?? (file.matches ? file.matches.length : 0),
          }));
          setCloudData(formatted);
        }
      }
    } catch {}
  };

  useEffect(() => {
    void fetchSources();
    void fetchExistingResults();
  }, []);

  const scanCloud = async () => {
    try {
      setLoading(true);
      setError(null);
      setStatusMessage(null);

      const res = await fetch(`${API}/cloud/scan-cloud`, {
        method: "POST",
      });

      const contentType = res.headers.get("content-type") || "";
      const data = contentType.includes("application/json")
        ? await res.json()
        : { detail: await res.text() };

      if (!res.ok) {
        throw new Error(data.detail || data.error || `Cloud scan failed (${res.status})`);
      }

      if (!data.results) {
        throw new Error("Cloud scan returned an invalid response.");
      }

      const formatted = data.results.map((file: any, index: number) => ({
        id: index,
        provider: file.provider,
        bucket: `${file.bucket}/${file.object_key}`,
        region: file.region,
        objects: 1,
        scanned: true,
        pii_found: file.pii_instance_count ?? 0,
      }));

      setCloudData(formatted);
      setStatusMessage(`Successfully scanned ${formatted.length} cloud object(s) across connected providers.`);
      void fetchSources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cloud scan failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bucketName.trim()) {
      setConnectError("Bucket or container name is required");
      return;
    }

    setConnectLoading(true);
    setConnectError(null);
    setConnectSuccess(null);

    try {
      const payload = {
        provider,
        bucket_or_container: bucketName.trim(),
        region,
        auth_method: authMethod,
        role_arn: roleArn.trim() || undefined,
        access_key_id: accessKeyId.trim() || undefined,
        secret_access_key: secretKey.trim() || undefined,
        service_account_email: serviceAccountEmail.trim() || undefined,
        connection_string: connectionString.trim() || undefined,
      };

      const res = await fetch(`${API}/cloud/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Failed to connect cloud provider");
      }

      setConnectSuccess(data.message || "Connected successfully!");
      setBucketName("");
      setRoleArn("");
      setAccessKeyId("");
      setSecretKey("");
      setServiceAccountEmail("");
      setConnectionString("");
      await fetchSources();
      await scanCloud();

      setTimeout(() => {
        setIsConnectOpen(false);
        setConnectSuccess(null);
      }, 1500);
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setConnectLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-card border border-border rounded-sm p-4 sovereign-shadow">
        <div>
          <h2 className="text-[14px] font-semibold text-foreground flex items-center gap-2">
            <Cloud className="h-4 w-4 text-primary" />
            Cloud Storage Connections
          </h2>
          <p className="text-[12px] text-muted-foreground mt-0.5">
            Connect corporate AWS S3, Azure Blob, and GCP buckets to discover PII and fulfill automated DSR requests.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setIsConnectOpen(true)}
            className="h-8 text-[12px] gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" />
            Connect Cloud Provider
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={scanCloud}
            className="h-8 text-[12px] gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Scanning Cloud..." : "Scan Cloud"}
          </Button>
        </div>
      </div>

      {statusMessage && (
        <div className="p-3 rounded-sm border border-primary/30 bg-primary/10 text-primary text-[12px] flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          {statusMessage}
        </div>
      )}

      {error && (
        <div className="rounded-sm border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          {error}
        </div>
      )}

      {/* Connected Cloud Accounts Summary */}
      {sources.length > 0 && (
        <div className="bg-card border border-border rounded-sm p-4 space-y-2.5 sovereign-shadow">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5" />
            Connected Cloud Repositories ({sources.length})
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {sources.map((s) => (
              <div
                key={s.id || s.bucket}
                className="rounded-sm border border-border bg-muted/20 p-3 space-y-1.5 text-[12px]"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">{s.provider}</span>
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px] uppercase font-mono">
                    <CheckCircle2 className="h-2.5 w-2.5" /> Connected
                  </span>
                </div>
                <div className="font-mono text-[11px] text-muted-foreground truncate" title={s.bucket}>
                  {s.bucket}
                </div>
                <div className="text-[11px] text-muted-foreground flex items-center justify-between pt-1 border-t border-border/50">
                  <span>Region: {s.region}</span>
                  <span className="text-[10px]">Auth: {s.auth_method || "IAM"}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scanned Cloud Objects Table */}
      <div className="bg-card border border-border rounded-sm overflow-hidden sovereign-shadow">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-foreground">
            Scanned Cloud Storage Objects
          </h3>
          <span className="text-[11px] text-muted-foreground font-mono">
            {cloudData.length} objects indexed
          </span>
        </div>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border bg-muted/20">
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Provider
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Bucket / Container / Key
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Region
              </th>
              <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Objects
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Scanned
              </th>
              <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                PII Found
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {cloudData.length > 0 ? (
              cloudData.map((c) => (
                <tr key={c.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <span
                      className={`px-2 py-0.5 text-[11px] font-medium rounded-sm border ${
                        c.provider.includes("AWS")
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                          : c.provider.includes("Azure")
                          ? "bg-sky-500/10 text-sky-400 border-sky-500/30"
                          : c.provider.includes("GCP")
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                          : "bg-muted text-muted-foreground border-border"
                      }`}
                    >
                      {c.provider}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-foreground max-w-xs truncate" title={c.bucket}>
                    {c.bucket}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground text-[12px] whitespace-nowrap">
                    {c.region}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-foreground">
                    {c.objects.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1.5 text-[12px] text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                      {c.scanned ? "Indexed" : "Pending"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono">
                    <span
                      className={
                        c.pii_found > 0
                          ? "text-amber-400 font-semibold"
                          : "text-muted-foreground"
                      }
                    >
                      {c.pii_found.toLocaleString()}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[12px] text-muted-foreground">
                  No cloud objects scanned yet. Click "Scan Cloud" or "Connect Cloud Provider" to index data.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-sm p-3 sovereign-shadow">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">
            Total Objects
          </div>
          <div className="text-xl font-bold text-foreground mt-1 font-mono">
            {cloudData.reduce((a, c) => a + c.objects, 0).toLocaleString()}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3 sovereign-shadow">
          <div className="text-[11px] text-amber-400 uppercase tracking-wider font-medium">
            PII Detected
          </div>
          <div className="text-xl font-bold text-amber-400 mt-1 font-mono">
            {cloudData.reduce((a, c) => a + c.pii_found, 0).toLocaleString()}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3 sovereign-shadow">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">
            Active Providers
          </div>
          <div className="text-xl font-bold text-foreground mt-1 font-mono">
            {new Set(cloudData.map((c) => c.provider)).size}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3 sovereign-shadow">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">
            Connected Buckets
          </div>
          <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">
            {sources.length || (cloudData.length ? 3 : 0)}
          </div>
        </div>
      </div>

      {/* Modal Dialog for Connect Cloud Provider */}
      {isConnectOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg bg-card border border-border rounded-sm shadow-xl overflow-hidden">
            <div className="flex items-center justify-between p-3.5 border-b border-border bg-muted/20">
              <div className="flex items-center gap-2">
                <Cloud className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Connect Cloud Storage Provider</h2>
              </div>
              <button
                type="button"
                onClick={() => setIsConnectOpen(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleConnect} className="p-4 space-y-3.5 text-[12px]">
              {connectError && (
                <div className="p-2.5 rounded-sm border border-destructive/30 bg-destructive/10 text-destructive text-[11px]">
                  {connectError}
                </div>
              )}
              {connectSuccess && (
                <div className="p-2.5 rounded-sm border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-[11px]">
                  {connectSuccess}
                </div>
              )}

              {/* Provider Selection */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Cloud Platform Provider
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(
                    [
                      { key: "AWS S3", label: "Amazon S3" },
                      { key: "Azure Blob Storage", label: "Azure Blob" },
                      { key: "GCP Cloud Storage", label: "Google Cloud" },
                    ] as const
                  ).map((p) => (
                    <button
                      key={p.key}
                      type="button"
                      onClick={() => {
                        setProvider(p.key);
                        if (p.key === "AWS S3") setRegion("ap-south-1 (Mumbai)");
                        else if (p.key === "Azure Blob Storage") setRegion("centralindia (Pune)");
                        else setRegion("asia-south1 (Mumbai)");
                      }}
                      className={`p-2 rounded-sm border text-[11px] text-center transition-colors ${
                        provider === p.key
                          ? "bg-primary/15 text-primary border-primary font-semibold"
                          : "border-border text-muted-foreground hover:bg-muted/30"
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Bucket / Container URI */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Bucket Name / Storage Container URI
                </label>
                <Input
                  value={bucketName}
                  onChange={(e) => setBucketName(e.target.value)}
                  placeholder={
                    provider === "AWS S3"
                      ? "e.g. company-production-vault"
                      : provider === "Azure Blob Storage"
                      ? "e.g. dpdp-compliance-container"
                      : "e.g. dpdp-analytics-archive"
                  }
                  className="h-8 text-[12px] font-mono"
                />
              </div>

              {/* Region */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Cloud Region
                </label>
                <Input
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  placeholder="e.g. ap-south-1 or us-east-1"
                  className="h-8 text-[12px]"
                />
              </div>

              {/* Authentication Type */}
              <div>
                <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Enterprise Authentication Method
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setAuthMethod("role_arn")}
                    className={`p-1.5 rounded-sm border text-[11px] text-left transition-colors ${
                      authMethod === "role_arn"
                        ? "bg-primary/15 text-primary border-primary font-medium"
                        : "border-border text-muted-foreground hover:bg-muted/30"
                    }`}
                  >
                    IAM Role ARN (Recommended)
                  </button>
                  <button
                    type="button"
                    onClick={() => setAuthMethod("access_keys")}
                    className={`p-1.5 rounded-sm border text-[11px] text-left transition-colors ${
                      authMethod === "access_keys"
                        ? "bg-primary/15 text-primary border-primary font-medium"
                        : "border-border text-muted-foreground hover:bg-muted/30"
                    }`}
                  >
                    Access Keys / Credentials
                  </button>
                </div>
              </div>

              {/* Auth Details Inputs */}
              {authMethod === "role_arn" ? (
                <div>
                  <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                    Cross-Account Role ARN
                  </label>
                  <Input
                    value={roleArn}
                    onChange={(e) => setRoleArn(e.target.value)}
                    placeholder="arn:aws:iam::123456789012:role/DPDPComplianceRole"
                    className="h-8 text-[12px] font-mono"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                    <Lock className="h-2.5 w-2.5 text-emerald-400" />
                    Zero-trust IAM delegation: No persistent secret credentials stored.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div>
                    <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                      Access Key ID / Client ID
                    </label>
                    <Input
                      value={accessKeyId}
                      onChange={(e) => setAccessKeyId(e.target.value)}
                      placeholder="AKIAIOSFODNN7EXAMPLE"
                      className="h-8 text-[12px] font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                      Secret Access Key / Token
                    </label>
                    <Input
                      type="password"
                      value={secretKey}
                      onChange={(e) => setSecretKey(e.target.value)}
                      placeholder="••••••••••••••••••••••••••••••••"
                      className="h-8 text-[12px] font-mono"
                    />
                  </div>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsConnectOpen(false)}
                  className="h-8 text-[12px]"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={connectLoading}
                  className="h-8 text-[12px]"
                >
                  {connectLoading ? "Validating & Connecting..." : "Connect Storage"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

