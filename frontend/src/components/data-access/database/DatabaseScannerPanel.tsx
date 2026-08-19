import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";

import {
  createConfiguredSupabaseSource,
  getDatabaseFindings,
  listDatabaseSources,
  listMyOrganisations,
  scanDatabaseSource,
  deleteUpdateDatabaseSource,
  maskDatabaseSource,
  type DatabaseFinding,
  type DatabaseSource,
  type OrganisationSummary,
} from "@/api/database";

import { useAppSelector } from "@/redux/hooks";

const riskColors: Record<string, string> = {
  critical: "bg-destructive/10 text-destructive",
  high: "bg-warning/10 text-warning",
  medium: "bg-primary/10 text-primary",
  low: "bg-muted text-muted-foreground",
};

function formatDate(value?: string | null): string {
  if (!value) return "Never";

  const parsed = new Date(value);

  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString();
}

export default function DatabaseScannerPanel() {
  const token = useAppSelector((state) => state.auth.token);
  const storedOrganisations = useAppSelector(
    (state) => state.auth.organisations,
  );

  const [organisations, setOrganisations] =
    useState<OrganisationSummary[]>(storedOrganisations);

  const [organisationId, setOrganisationId] = useState(
    storedOrganisations[0]?.id || "",
  );

  const [sources, setSources] = useState<DatabaseSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [findings, setFindings] = useState<DatabaseFinding[]>([]);

  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [scanAuth, setScanAuth] = useState(false);

  const [remediateIdentifier, setRemediateIdentifier] = useState("");
  const [remediateAction, setRemediateAction] = useState<"UPDATE" | "DELETE" | "MASK">("UPDATE");
  const [remediateReplacement, setRemediateReplacement] = useState("");
  const [remediateResult, setRemediateResult] = useState<{
    impacted_locations: number;
    impacted_rows: number;
  } | null>(null);

  const selectedSource = useMemo(
    () =>
      sources.find((source) => source.id === selectedSourceId) || null,
    [sources, selectedSourceId],
  );

  const refreshOrganisations = useCallback(async () => {
    if (!token) {
      setError("Please sign in first.");
      return;
    }

    setBusy("organisations");
    setError("");

    try {
      const response = await listMyOrganisations(token);

      setOrganisations(response.organisations);

      if (!response.organisations.length) {
        setError("You are not in an organisation yet. Join an organisation from Profile using an invite code, then try again.");
      }

      setOrganisationId((current) => {
        if (
          current &&
          response.organisations.some(
            (organisation) => organisation.id === current,
          )
        ) {
          return current;
        }

        return response.organisations[0]?.id || "";
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load organisations.",
      );
    } finally {
      setBusy("");
    }
  }, [token]);

  const loadSources = useCallback(
    async (nextOrganisationId: string) => {
      if (!token || !nextOrganisationId) {
        setSources([]);
        setSelectedSourceId("");
        setFindings([]);
        return;
      }

      setBusy("sources");
      setError("");

      try {
        const response = await listDatabaseSources(
          token,
          nextOrganisationId,
        );

        setSources(response.sources);

        setSelectedSourceId((current) => {
          if (
            current &&
            response.sources.some((source) => source.id === current)
          ) {
            return current;
          }

          return response.sources[0]?.id || "";
        });
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Could not load database sources.",
        );
      } finally {
        setBusy("");
      }
    },
    [token],
  );

  useEffect(() => {
    void refreshOrganisations();
  }, [refreshOrganisations]);

  useEffect(() => {
    void loadSources(organisationId);
  }, [organisationId, loadSources]);

  const connectSupabase = async () => {
    if (!token) {
      setError("Please sign in first.");
      return;
    }

    if (!organisationId) {
      setError("Select an organisation first.");
      return;
    }

    setBusy("connect");
    setError("");
    setMessage("");

    try {
      /*
       * IMPORTANT:
       * No database credentials are sent here.
       *
       * The backend reads:
       * DPDP_DB_SUPABASE_HOST
       * DPDP_DB_SUPABASE_PORT
       * DPDP_DB_SUPABASE_NAME
       * DPDP_DB_SUPABASE_USER
       * DPDP_DB_SUPABASE_PASSWORD
       */
      const response = await createConfiguredSupabaseSource(
        token,
        organisationId,
      );

      setMessage(
        `Connected to ${response.source.display_name}.`,
      );

      await loadSources(organisationId);

      setSelectedSourceId(response.source.id);
      setFindings([]);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not connect to the configured Supabase database.",
      );
    } finally {
      setBusy("");
    }
  };

  const selectSource = async (sourceId: string) => {
    setSelectedSourceId(sourceId);
    setFindings([]);
    setError("");
    setMessage("");
    setRemediateIdentifier("");
    setRemediateAction("UPDATE");
    setRemediateReplacement("");
    setRemediateResult(null);

    if (!token || !organisationId || !sourceId) {
      return;
    }

    setBusy("findings");

    try {
      const response = await getDatabaseFindings(
        token,
        organisationId,
        sourceId,
      );

      setFindings(response.findings);
    } catch (caught) {
      /*
       * A newly-created source has no findings yet.
       * A 404 here is therefore not necessarily a real problem.
       */
      setFindings([]);

      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load database findings.",
      );
    } finally {
      setBusy("");
    }
  };

  const scanSelectedSource = async () => {
    if (!token) {
      setError("Please sign in first.");
      return;
    }

    if (!organisationId || !selectedSourceId) {
      setError("Select a database source first.");
      return;
    }

    setBusy("scan");
    setError("");
    setMessage("");

    try {
      const response = await scanDatabaseSource(
        token,
        organisationId,
        selectedSourceId,
        scanAuth,
      );

      setFindings(response.findings);

      const summary = response.summary;

      setMessage(
        `Scan completed: ${summary.finding_count || 0
        } PII finding(s) across ${summary.scanned_tables || 0
        } table(s), ${summary.inspected_columns || 0
        } columns and ${summary.sampled_values || 0
        } sampled values.`,
      );

      if (response.warnings.length > 0) {
        setMessage(
          (current) =>
            `${current} ${response.warnings.length} warning(s) recorded.`,
        );
      }

      await loadSources(organisationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Database scan failed.",
      );
    } finally {
      setBusy("");
    }
  };

  const executeRemediation = async () => {
    if (!token) {
      setError("Please sign in first.");
      return;
    }

    if (!organisationId || !selectedSourceId) {
      setError("Select a database source first.");
      return;
    }

    setBusy("remediate");
    setError("");
    setMessage("");
    setRemediateResult(null);

    try {
      const response = remediateAction === "MASK"
        ? await maskDatabaseSource(
            token,
            organisationId,
            selectedSourceId,
            remediateIdentifier,
          )
        : await deleteUpdateDatabaseSource(
            token,
            organisationId,
            selectedSourceId,
            remediateIdentifier,
            remediateAction,
            remediateAction === "UPDATE" ? (remediateReplacement || "[REDACTED]") : null,
          );

      setRemediateResult({
        impacted_locations: response.impacted_locations,
        impacted_rows: response.impacted_rows,
      });

      setMessage(
        `Changes made successfully. ${remediateAction === "UPDATE" ? "Redacted" : remediateAction === "MASK" ? "Masked" : "Deleted"
        } target PII value across ${response.impacted_locations} table(s), affecting ${response.impacted_rows
        } row(s).`,
      );

      // Trigger findings and sources reload
      await selectSource(selectedSourceId);
      await loadSources(organisationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Database remediation failed.",
      );
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-sm border border-border bg-card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-[13px] font-semibold text-foreground">
              Database PII Discovery
            </h3>

            <p className="mt-1 max-w-2xl text-[12px] text-muted-foreground">
              Scan a configured PostgreSQL database for PII using
              metadata and sampled values. Database access is read-only
              and raw PII values are never displayed here.
            </p>
          </div>

          <Button
            variant="outline"
            onClick={() => void refreshOrganisations()}
            disabled={busy !== ""}
          >
            {busy === "organisations"
              ? "Refreshing..."
              : "Refresh organisations"}
          </Button>
        </div>

        <div className="mt-4 max-w-md space-y-1.5">
          <label
            htmlFor="database-organisation"
            className="text-[12px] text-muted-foreground"
          >
            Organisation
          </label>

          <select
            id="database-organisation"
            className="h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
            value={organisationId}
            onChange={(event) =>
              setOrganisationId(event.target.value)
            }
          >
            <option value="">Select an organisation</option>

            {organisations.map((organisation) => (
              <option
                key={organisation.id}
                value={organisation.id}
              >
                {organisation.name} (
                {organisation.role || "member"})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Supabase connection */}
      <div className="rounded-sm border border-border bg-card p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-[13px] font-semibold text-foreground">
              Live PostgreSQL database
            </h3>

            <p className="mt-1 text-[12px] text-muted-foreground">
              Connect the Supabase PostgreSQL database configured in
              the backend environment.
            </p>

            <p className="mt-1 text-[11px] text-muted-foreground">
              Database credentials stay on the backend and are never
              sent to the browser.
            </p>
          </div>

          <Button
            onClick={() => void connectSupabase()}
            disabled={
              busy !== "" || !organisationId || !token
            }
          >
            {busy === "connect"
              ? "Connecting..."
              : "Connect Supabase"}
          </Button>
        </div>
      </div>

      {/* Messages */}
      {error ? (
        <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          {error}
        </div>
      ) : null}

      {message ? (
        <div className="rounded-sm border border-primary/30 bg-primary/10 px-3 py-2 text-[12px] text-primary">
          {message}
        </div>
      ) : null}

      {/* Sources */}
      <div className="overflow-hidden rounded-sm border border-border bg-card">
        <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-3">
          <div>
            <h3 className="text-[13px] font-semibold text-foreground">
              Database connections
            </h3>

            <p className="mt-1 text-[11px] text-muted-foreground">
              Registered database sources for this organisation.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() =>
                void loadSources(organisationId)
              }
              disabled={busy !== "" || !organisationId}
            >
              {busy === "sources"
                ? "Refreshing..."
                : "Refresh"}
            </Button>

            {selectedSource ? (
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={scanAuth}
                    onChange={(e) => setScanAuth(e.target.checked)}
                    className="rounded border-border bg-background"
                  />
                  Scan auth schemas
                </label>

                <Button
                  onClick={() => void scanSelectedSource()}
                  disabled={busy !== ""}
                >
                  {busy === "scan"
                    ? "Scanning..."
                    : "Run PII Scan"}
                </Button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border bg-muted/20">
                <th className="px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Source
                </th>

                <th className="px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Connection
                </th>

                <th className="px-4 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  PII findings
                </th>

                <th className="px-4 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Tables
                </th>

                <th className="px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Last scan
                </th>

                <th className="px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-border">
              {sources.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    No database source connected yet.
                    <br />
                    <span className="text-[11px]">
                      Click "Connect Supabase" above.
                    </span>
                  </td>
                </tr>
              ) : (
                sources.map((source) => (
                  <tr
                    key={source.id}
                    onClick={() =>
                      void selectSource(source.id)
                    }
                    className={`cursor-pointer hover:bg-muted/20 ${selectedSourceId === source.id
                      ? "bg-primary/5"
                      : ""
                      }`}
                  >
                    <td className="px-4 py-2.5 font-medium text-foreground">
                      {source.display_name}
                    </td>

                    <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">
                      {source.connection_label}
                    </td>

                    <td className="px-4 py-2.5 text-right font-mono text-foreground">
                      {source.latest_summary?.finding_count || 0}
                    </td>

                    <td className="px-4 py-2.5 text-right font-mono text-foreground">
                      {source.latest_summary?.scanned_tables || 0}
                    </td>

                    <td className="px-4 py-2.5 text-muted-foreground">
                      {formatDate(source.last_scan_at)}
                    </td>

                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-flex items-center gap-1.5 text-[12px] capitalize ${source.last_scan_status ===
                          "completed"
                          ? "text-primary"
                          : source.last_scan_status ===
                            "failed"
                            ? "text-destructive"
                            : "text-muted-foreground"
                          }`}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                        {source.last_scan_status ||
                          "not scanned"}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary */}
      {selectedSource ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-sm border border-border bg-card p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Tables scanned
            </p>

            <p className="mt-1 font-mono text-xl font-semibold">
              {selectedSource.latest_summary?.scanned_tables ||
                0}
            </p>
          </div>

          <div className="rounded-sm border border-border bg-card p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Columns inspected
            </p>

            <p className="mt-1 font-mono text-xl font-semibold">
              {selectedSource.latest_summary
                ?.inspected_columns || 0}
            </p>
          </div>

          <div className="rounded-sm border border-border bg-card p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Values sampled
            </p>

            <p className="mt-1 font-mono text-xl font-semibold">
              {selectedSource.latest_summary?.sampled_values ||
                0}
            </p>
          </div>

          <div className="rounded-sm border border-border bg-card p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              PII findings
            </p>

            <p className="mt-1 font-mono text-xl font-semibold">
              {selectedSource.latest_summary?.finding_count ||
                0}
            </p>
          </div>
        </div>
      ) : null}

      {/* Remediation Panel */}
      {selectedSource ? (
        <div className="rounded-sm border border-border bg-card p-4">
          <h3 className="text-[13px] font-semibold text-foreground">
            Database PII Redaction & Deletion
          </h3>

          <p className="mt-1 text-[12px] text-muted-foreground">
            Search for a specific PII value across all sampleable columns in this database to redact it using SQL REPLACE or delete the matching rows.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label
                htmlFor="remediate-identifier"
                className="text-[12px] text-muted-foreground"
              >
                Target PII Value
              </label>

              <input
                id="remediate-identifier"
                type="text"
                className="h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
                placeholder="e.g. john.doe@example.com"
                value={remediateIdentifier}
                onChange={(e) => setRemediateIdentifier(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="remediate-action"
                className="text-[12px] text-muted-foreground"
              >
                Action
              </label>

              <select
                id="remediate-action"
                className="h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
                value={remediateAction}
                onChange={(e) =>
                  setRemediateAction(
                    e.target.value as "UPDATE" | "DELETE" | "MASK",
                  )
                }
              >
                <option value="UPDATE">Redact (SQL REPLACE)</option>

                <option value="MASK">Mask (same as local agent)</option>

                <option value="DELETE">Delete Row</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="remediate-replacement"
                className="text-[12px] text-muted-foreground"
              >
                Replacement Value
              </label>

              <input
                id="remediate-replacement"
                type="text"
                className="h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
                placeholder="[REDACTED]"
                disabled={remediateAction !== "UPDATE"}
                value={remediateReplacement}
                onChange={(e) => setRemediateReplacement(e.target.value)}
              />
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between">
            <div>
              {remediateResult ? (
                <p className="text-[12px] text-primary">
                  Success! Impacted {remediateResult.impacted_locations}{" "}
                  location(s) and {remediateResult.impacted_rows} row(s).
                </p>
              ) : null}
            </div>

            <Button
              onClick={() => void executeRemediation()}
              disabled={busy !== "" || !remediateIdentifier}
            >
              {busy === "remediate"
                ? "Executing..."
                : "Execute Remediation"}
            </Button>
          </div>
        </div>
      ) : null}

      {/* Findings */}
      {selectedSource ? (
        <div className="overflow-hidden rounded-sm border border-border bg-card">
          <div className="border-b border-border bg-muted/30 px-4 py-3">
            <h3 className="text-[13px] font-semibold text-foreground">
              PII findings — {selectedSource.display_name}
            </h3>

            <p className="mt-1 text-[11px] text-muted-foreground">
              Findings identify the table/column and detection
              evidence. Raw PII values are never displayed.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-muted/20">
                  {[
                    "Location",
                    "PII type",
                    "Method",
                    "Confidence",
                    "Samples / hits",
                    "Risk",
                    "Recommended action",
                  ].map((heading) => (
                    <th
                      key={heading}
                      className="px-4 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody className="divide-y divide-border">
                {busy === "findings" ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      Loading findings...
                    </td>
                  </tr>
                ) : null}

                {busy !== "findings" &&
                  findings.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No findings yet.
                      <br />
                      <span className="text-[11px]">
                        Click "Run PII Scan" to scan this
                        database.
                      </span>
                    </td>
                  </tr>
                ) : null}

                {findings.map((finding) => (
                  <tr
                    key={`${finding.location}-${finding.pii_type}`}
                    className="hover:bg-muted/20"
                  >
                    <td className="px-4 py-2.5 font-mono text-[12px] text-foreground">
                      {finding.location}
                    </td>

                    <td className="px-4 py-2.5 font-medium text-foreground">
                      {finding.pii_type}
                    </td>

                    <td className="px-4 py-2.5 text-muted-foreground">
                      {finding.method}
                    </td>

                    <td className="px-4 py-2.5 font-mono text-foreground">
                      {Math.round(
                        finding.confidence * 100,
                      )}
                      %
                    </td>

                    <td className="px-4 py-2.5 font-mono text-foreground">
                      {finding.sample_count} /{" "}
                      {finding.match_count}
                    </td>

                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-sm px-2 py-0.5 text-[11px] font-medium uppercase ${riskColors[finding.risk] ||
                          riskColors.medium
                          }`}
                      >
                        {finding.risk}
                      </span>
                    </td>

                    <td className="px-4 py-2.5 capitalize text-muted-foreground">
                      {finding.recommended_action}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}