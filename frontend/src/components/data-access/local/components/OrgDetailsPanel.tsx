import React from "react";
import { Input } from "@/components/ui/input";
import type { OrganisationInfo } from "../../../../api/localAgent";

interface Props {
  orgs: OrganisationInfo[];
  selectedOrgId: string;
  orgName: string;
  orgId: string;
  adminKey: string;
  agentToken: string;
  orgsLoading: boolean;
  onSelectOrg: (id: string) => void;
}

export function OrgDetailsPanel({
  orgs, selectedOrgId, orgName, orgId,
  adminKey, agentToken, orgsLoading, onSelectOrg,
}: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {orgs.length > 1 ? (
        <label className="text-[12px] text-foreground/90 md:col-span-2">
          Select Organisation
          <select
            className="mt-1 h-10 w-full rounded-sm border border-border bg-background px-3 text-sm"
            value={selectedOrgId}
            onChange={(e) => onSelectOrg(e.target.value)}
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
            value={orgs[0] ? `${orgs[0].name} (${orgs[0].role || "member"})` : ""}
            readOnly
            placeholder={orgsLoading ? "Loading organisation..." : "No organisation linked"}
          />
        </label>
      )}

      <label className="text-[12px] text-foreground/90">
        Organisation Name
        <Input className="mt-1" value={orgName} readOnly placeholder="-" />
      </label>

      <label className="text-[12px] text-foreground/90">
        Organisation ID
        <Input className="mt-1" value={orgId} readOnly placeholder="Select an organisation" />
      </label>

      <label className="text-[12px] text-foreground/90">
        Admin Key
        <Input className="mt-1" type="password" value={adminKey} readOnly
          placeholder="No admin key synced from login" />
      </label>

      <label className="text-[12px] text-foreground/90">
        Agent Token
        <Input className="mt-1" type="password" value={agentToken} readOnly
          placeholder="No agent token synced from login" />
      </label>
    </div>
  );
}