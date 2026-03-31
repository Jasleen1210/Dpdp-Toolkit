import React, { useMemo } from "react";
import { Eye } from "lucide-react";
import type {
  FileEntry,
  FileStats,
  DirNode,
  FileCategories,
} from "./LocalFilesPanel";

interface LocalScanResultsProps {
  stats: FileStats;
  fileCategories: FileCategories;
  filesByType: Record<string, FileEntry[]>;
  getFileIcon: (name: string) => React.ReactNode;
  openCategory: string | null;
  setOpenCategory: React.Dispatch<React.SetStateAction<string | null>>;
  scannedFiles: FileEntry[];
  fileListLimit: number;
  setFileListLimit: React.Dispatch<React.SetStateAction<number>>;
  openFile: (file: FileEntry) => void;
  piiResults: any[];
  rootDirs: DirNode[];
  formatBytes: (bytes: number) => string;
}

const LocalScanResults: React.FC<LocalScanResultsProps> = ({
  stats,
  fileCategories,
  filesByType,
  getFileIcon,
  openCategory,
  setOpenCategory,
  scannedFiles,
  fileListLimit,
  setFileListLimit,
  openFile,
  piiResults,
  rootDirs,
  formatBytes,
}) => {
  const piiStats = useMemo(() => {
    const summary: Record<string, number> = {};
    for (const r of piiResults) {
      for (const [k, v] of Object.entries(r.pii || {})) {
        if (v) summary[k] = (summary[k] || 0) + 1;
      }
    }
    return summary;
  }, [piiResults]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Total Files
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {stats.total.toLocaleString()}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Total Size
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {formatBytes(stats.totalSize)}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            File Types
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {Object.keys(stats.byType).length}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Directories
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {rootDirs.length}
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <h3 className="text-[13px] font-semibold text-foreground">
          File Distribution
        </h3>
        <div className="space-y-2">
          {Object.entries(stats.byType)
            .sort(([, a], [, b]) => b.count - a.count)
            .map(([cat, data]) => {
              const pct = (data.count / stats.total) * 100;
              return (
                <div key={cat} className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 text-[11px] min-w-[140px]">
                    <span className="text-primary">{data.icon}</span>
                    <span className="text-foreground font-medium">
                      {fileCategories[cat]?.label || "Other"}
                    </span>
                  </div>
                  <progress
                    value={pct}
                    max={100}
                    className="progress-bar flex-1"
                    aria-label={`${fileCategories[cat]?.label || "Other"} share`}
                  />
                  <span className="text-[11px] text-muted-foreground w-12 text-right">
                    {pct.toFixed(1)}%
                  </span>
                  <span className="text-[11px] text-muted-foreground w-12 text-right">
                    {data.count}
                  </span>
                </div>
              );
            })}
        </div>
      </div>

      {piiResults.length > 0 && (
        <div className="bg-card border border-border rounded-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-foreground">
              PII Detection Results
            </h3>
            <span className="text-[11px] text-muted-foreground">
              {piiResults.length} files scanned
            </span>
          </div>
          <div className="max-h-[300px] overflow-y-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-2 text-[11px] uppercase text-muted-foreground">
                    File
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] uppercase text-muted-foreground">
                    Detected PII
                  </th>
                  <th className="text-right px-4 py-2 text-[11px] uppercase text-muted-foreground">
                    Risk
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {piiResults.map((r, i) => {
                  const detected = Object.entries(r.pii || {})
                    .filter(([, v]) => v)
                    .map(([k]) => k);
                  const riskLevel =
                    detected.length === 0
                      ? "Low"
                      : detected.length <= 2
                        ? "Medium"
                        : "High";
                  return (
                    <tr key={i} className="hover:bg-muted/20">
                      <td className="px-4 py-2 font-mono text-foreground">
                        {r.file}
                      </td>
                      <td className="px-4 py-2">
                        {detected.length === 0 ? (
                          <span className="text-muted-foreground text-[11px]">
                            No PII found
                          </span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {detected.map((type) => (
                              <span
                                key={type}
                                className="px-2 py-0.5 text-[10px] bg-muted rounded text-foreground"
                              >
                                {type}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            riskLevel === "Low"
                              ? "bg-green-500/10 text-green-600"
                              : riskLevel === "Medium"
                                ? "bg-yellow-500/10 text-yellow-600"
                                : "bg-red-500/10 text-red-600"
                          }`}
                        >
                          {riskLevel}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30">
          <h3 className="text-[13px] font-semibold text-foreground">
            File Type Breakdown
          </h3>
        </div>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border bg-muted/20">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Type
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Count
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Size
              </th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Distribution
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Files
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {Object.entries(stats.byType)
              .sort(([, a], [, b]) => b.count - a.count)
              .map(([cat, data]) => (
                <React.Fragment key={cat}>
                  <tr className="hover:bg-muted/20">
                    <td className="px-4 py-2.5 flex items-center gap-2">
                      <span className="text-primary">{data.icon}</span>
                      <span className="font-medium text-foreground capitalize">
                        {fileCategories[cat]?.label || "Other Files"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-foreground">
                      {data.count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">
                      {formatBytes(data.size)}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <progress
                          value={(data.count / stats.total) * 100}
                          max={100}
                          className="progress-bar flex-1"
                          aria-label={`Share for ${fileCategories[cat]?.label || "Other Files"}`}
                        />
                        <span className="text-[11px] text-muted-foreground w-10 text-right">
                          {((data.count / stats.total) * 100).toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() =>
                          setOpenCategory(openCategory === cat ? null : cat)
                        }
                        className="text-[11px] font-semibold text-primary hover:text-primary/80"
                      >
                        {openCategory === cat ? "Hide" : "Show"} 10
                      </button>
                    </td>
                  </tr>
                  {openCategory === cat && (
                    <tr className="bg-muted/10">
                      <td colSpan={5} className="px-4 py-2">
                        <div className="flex flex-wrap gap-2">
                          {(filesByType[cat] || []).length === 0 && (
                            <span className="text-[11px] text-muted-foreground">
                              No files captured for this type.
                            </span>
                          )}
                          {(filesByType[cat] || []).map((file) => (
                            <div
                              key={file.path}
                              className="px-2 py-1 bg-card border border-border rounded-sm text-[11px] flex items-center gap-2"
                            >
                              {getFileIcon(file.name)}
                              <span className="font-mono text-foreground truncate max-w-[200px]">
                                {file.name}
                              </span>
                              <span className="text-muted-foreground truncate max-w-[240px]">
                                {file.path}
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
          </tbody>
        </table>
      </div>

      <div className="bg-card border border-border rounded-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-foreground">
            Scanned Files
          </h3>
          <span className="text-[11px] text-muted-foreground">
            {scannedFiles.length.toLocaleString()} total
          </span>
        </div>
        <div className="max-h-[400px] overflow-y-auto">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                  File
                </th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                  Path
                </th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                  Size
                </th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                  Type
                </th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                  Open
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {scannedFiles.slice(0, fileListLimit).map((f, i) => (
                <tr key={i} className="hover:bg-muted/20">
                  <td className="px-4 py-1.5">
                    <button
                      onClick={() => openFile(f)}
                      className="flex items-center gap-1.5 text-left w-full hover:text-primary"
                    >
                      {getFileIcon(f.name)}
                      <span className="font-mono text-foreground truncate max-w-[200px]">
                        {f.name}
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-1.5 font-mono text-muted-foreground truncate max-w-[300px]">
                    {f.path}
                  </td>
                  <td className="px-4 py-1.5 text-right font-mono text-muted-foreground">
                    {f.size ? formatBytes(f.size) : "—"}
                  </td>
                  <td className="px-4 py-1.5">
                    <span className="px-1.5 py-0.5 text-[10px] bg-muted rounded-sm text-muted-foreground uppercase">
                      {f.extension || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-1.5 text-right">
                    <button
                      onClick={() => openFile(f)}
                      className="inline-flex items-center gap-1 text-primary hover:text-primary/80"
                      aria-label={`Open ${f.name}`}
                      title={`Open ${f.name}`}
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {scannedFiles.length > 0 && scannedFiles.length > fileListLimit && (
          <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-muted/20 text-[11px] text-muted-foreground">
            <span>
              Showing {fileListLimit.toLocaleString()} of{" "}
              {scannedFiles.length.toLocaleString()} files
            </span>
            <button
              onClick={() => setFileListLimit(scannedFiles.length)}
              className="text-primary hover:text-primary/80 font-semibold text-[11px]"
            >
              Show all
            </button>
          </div>
        )}
        {scannedFiles.length > 100 && fileListLimit === scannedFiles.length && (
          <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-muted/20 text-[11px] text-muted-foreground">
            <span>
              Showing all {scannedFiles.length.toLocaleString()} files
            </span>
            <button
              onClick={() =>
                setFileListLimit(Math.min(100, scannedFiles.length))
              }
              className="text-primary hover:text-primary/80 font-semibold text-[11px]"
            >
              Collapse to first 100
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default LocalScanResults;
