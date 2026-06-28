import React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Device } from "../../../../api/localAgent";

interface Props {
  actionType: "access" | "update" | "delete";
  query: string;
  newValue: string;
  expiresInHours: number;
  approvedDevices: Device[];
  taskTargetDeviceIds: string[];
  loading: boolean;
  onActionTypeChange: (v: "access" | "update" | "delete") => void;
  onQueryChange: (v: string) => void;
  onNewValueChange: (v: string) => void;
  onExpiresChange: (v: number) => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onToggleDevice: (id: string, checked: boolean) => void;
  onCreateTask: () => void;
  onFetchResults: () => void;
}

export function TaskForm({
  actionType, query, newValue, expiresInHours,
  approvedDevices, taskTargetDeviceIds, loading,
  onActionTypeChange, onQueryChange, onNewValueChange,
  onExpiresChange, onSelectAll, onClearSelection,
  onToggleDevice, onCreateTask, onFetchResults,
}: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="text-[12px] text-foreground/90 md:col-span-2">
        <span className="block mb-1.5 font-medium">Action Type</span>
        <div className="flex gap-4 items-center bg-muted/20 p-2 rounded-sm border border-border">
          {(["access", "update", "delete"] as const).map((type) => (
            <label key={type} className="flex items-center gap-2 capitalize cursor-pointer">
              <input
                type="radio"
                name="actionType"
                value={type}
                checked={actionType === type}
                onChange={() => onActionTypeChange(type)}
                className="accent-primary h-3.5 w-3.5"
              />
              <span className="text-foreground">{type}</span>
            </label>
          ))}
        </div>
      </div>

      <label className="text-[12px] text-foreground/90 md:col-span-2">
        {actionType === "access" ? "Access Query" : "Target Value (Old PII)"}
        <Input
          className="mt-1"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={actionType === "access" ? "rahul@gmail.com" : "old-value@domain.com"}
        />
      </label>

      {actionType === "update" && (
        <label className="text-[12px] text-foreground/90 md:col-span-2">
          New Value (New PII)
          <Input
            className="mt-1"
            value={newValue}
            onChange={(e) => onNewValueChange(e.target.value)}
            placeholder="new-value@domain.com"
          />
        </label>
      )}

      <label className="text-[12px] text-foreground/90 md:col-span-2">
        Expires In Hours (max 24)
        <Input
          className="mt-1"
          type="number"
          min={1}
          max={24}
          value={expiresInHours}
          onChange={(e) => onExpiresChange(Number(e.target.value || 24))}
          placeholder="24"
        />
      </label>

      <div className="text-[12px] text-foreground/90 md:col-span-2">
        Target Devices
        {approvedDevices.length === 0 ? (
          <div className="mt-1 rounded-sm border border-border bg-muted/30 px-3 py-2 text-muted-foreground">
            No approved devices available. Approve devices first.
          </div>
        ) : (
          <div className="mt-1 space-y-2 rounded-sm border border-border bg-muted/20 p-2">
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" variant="outline" onClick={onSelectAll}>
                Select All Approved
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={onClearSelection}>
                Clear Selection
              </Button>
            </div>
            <div className="space-y-1 max-h-36 overflow-auto pr-1">
              {approvedDevices.map((d) => (
                <label key={`task-target-${d.device_id}`}
                  className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={taskTargetDeviceIds.includes(d.device_id)}
                    onChange={(e) => onToggleDevice(d.device_id, e.target.checked)}
                  />
                  <span className="text-foreground">{d.device_id}</span>
                  <span className="text-muted-foreground">({d.hostname || "unknown-host"})</span>
                </label>
              ))}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {taskTargetDeviceIds.length > 0
                ? `Selected ${taskTargetDeviceIds.length} device(s)`
                : "No devices selected. Task will run on all approved devices."}
            </div>
          </div>
        )}
      </div>

      <div className="md:col-span-2 flex flex-wrap gap-2">
        <Button onClick={onCreateTask} disabled={loading}>Create Task</Button>
        <Button variant="outline" onClick={onFetchResults} disabled={loading}>
          Fetch Task Group Results
        </Button>
      </div>
    </div>
  );
}