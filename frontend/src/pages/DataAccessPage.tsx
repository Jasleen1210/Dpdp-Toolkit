import React, { useState } from "react";
import { HardDrive, Database, Cloud } from "lucide-react";
import LocalFilesPanel from "../components/data-access/local/LocalFilesPanel";
import DatabasePanel from "../components/data-access/database/DatabasePanel";
import CloudPanel from "../components/data-access/cloud/CloudPanel";
import RequestPanel from "../components/data-access/cloud/RequestPanel";

type AccessMode = "local" | "db" | "cloud";

function ModeSelector({
  mode,
  setMode,
}: {
  mode: AccessMode;
  setMode: (m: AccessMode) => void;
}) {
  const modes: {
    key: AccessMode;
    label: string;
    desc: string;
    icon: React.ReactNode;
  }[] = [
    {
      key: "local",
      label: "Local Files",
      desc: "Scan local filesystem directories",
      icon: <HardDrive className="w-6 h-6" />,
    },
    {
      key: "db",
      label: "Database",
      desc: "Connect to database sources",
      icon: <Database className="w-6 h-6" />,
    },
    {
      key: "cloud",
      label: "Cloud Storage",
      desc: "AWS S3, Azure Blob, GCP",
      icon: <Cloud className="w-6 h-6" />,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {modes.map((m) => (
        <button
          key={m.key}
          onClick={() => setMode(m.key)}
          className={`flex items-center gap-3 p-4 rounded-sm border transition-all text-left ${
            mode === m.key
              ? "border-primary bg-primary/10 text-primary"
              : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:bg-muted/30"
          }`}
        >
          <div
            className={
              mode === m.key ? "text-primary" : "text-muted-foreground"
            }
          >
            {m.icon}
          </div>
          <div>
            <div className="text-[13px] font-semibold">{m.label}</div>
            <div className="text-[11px] opacity-70">{m.desc}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

export default function DataAccessPage() {
  const [mode, setMode] = useState<AccessMode>("local");

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground">Access Data</h1>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          Connect and scan data from local files, databases, or cloud storage
        </p>
      </div>

      <ModeSelector mode={mode} setMode={setMode} />

      {mode === "local" && <LocalFilesPanel />}
      {mode === "db" && <DatabasePanel />}
      {mode === "cloud" && (
        <>
          <CloudPanel />
          {/* <RequestPanel /> */}
        </>
      )}
    </div>
  );
}
  