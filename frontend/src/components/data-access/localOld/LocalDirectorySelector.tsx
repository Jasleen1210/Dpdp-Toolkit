import React from "react";
import {
  HardDrive,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Check,
  X,
  Loader2,
  Eye,
} from "lucide-react";
import type { DirNode, FileEntry, DirProgress } from "./LocalFilesPanel";

interface LocalDirectorySelectorProps {
  rootDirs: DirNode[];
  treeFiles: Record<string, FileEntry[]>;
  dirProgress: Record<string, DirProgress>;
  scanning: boolean;
  addDirectory: () => Promise<void>;
  addFiles: () => Promise<void>;
  removeDir: (path: string) => void;
  removeFile: (path: string) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  dragActive: boolean;
  toggleExpand: (path: string) => Promise<void> | void;
  toggleSelect: (path: string) => void;
  openFile: (file: FileEntry) => void;
  getFileIcon: (name: string) => React.ReactNode;
  formatBytes: (bytes: number) => string;
}

interface DirTreeProps {
  nodes: DirNode[];
  depth?: number;
  treeFiles: Record<string, FileEntry[]>;
  toggleExpand: (path: string) => Promise<void> | void;
  toggleSelect: (path: string) => void;
  scanning: boolean;
  dirProgress: Record<string, DirProgress>;
  getFileIcon: (name: string) => React.ReactNode;
  openFile: (file: FileEntry) => void;
  formatBytes: (bytes: number) => string;
  removeFile: (path: string) => void;
}

const DirTree: React.FC<DirTreeProps> = ({
  nodes,
  depth = 0,
  treeFiles,
  toggleExpand,
  toggleSelect,
  scanning,
  dirProgress,
  getFileIcon,
  openFile,
  formatBytes,
  removeFile,
}) => (
  <div className={depth > 0 ? "ml-4 border-l border-border/50 pl-1" : ""}>
    {nodes.map((n) => (
      <div key={n.path}>
        <div className="flex items-center gap-1.5 py-1 px-1 hover:bg-muted/20 rounded-sm group">
          <button
            onClick={() => toggleExpand(n.path)}
            className="p-0.5 text-muted-foreground hover:text-foreground shrink-0"
          >
            {n.loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
            ) : n.expanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
          </button>
          <button
            onClick={() => toggleSelect(n.path)}
            className={`w-4 h-4 rounded-sm border flex items-center justify-center shrink-0 transition-colors ${
              n.selected
                ? "bg-primary border-primary text-primary-foreground"
                : "border-muted-foreground/50"
            }`}
          >
            {n.selected && <Check className="w-2.5 h-2.5" />}
          </button>
          <FolderOpen
            className={`w-4 h-4 shrink-0 ${n.selected ? "text-primary" : "text-muted-foreground"}`}
          />
          <span className="text-[12px] text-foreground truncate font-medium">
            {n.name}
          </span>
          {n.children.length > 0 && (
            <span className="text-[10px] text-muted-foreground ml-1 shrink-0">
              ({n.children.length} folder{n.children.length !== 1 ? "s" : ""}
              {treeFiles[n.path]
                ? `, ${treeFiles[n.path].length} file${treeFiles[n.path].length !== 1 ? "s" : ""}`
                : ""}
              )
            </span>
          )}
          {!n.children.length && treeFiles[n.path] && (
            <span className="text-[10px] text-muted-foreground ml-1 shrink-0">
              ({treeFiles[n.path].length} file
              {treeFiles[n.path].length !== 1 ? "s" : ""})
            </span>
          )}
          {scanning &&
            dirProgress[n.path] &&
            (() => {
              const prog = dirProgress[n.path];
              const pct = Math.min(
                100,
                Math.round((prog.processed / Math.max(prog.total, 1)) * 100),
              );
              return (
                <div className="ml-auto flex items-center gap-2">
                  <progress
                    value={pct}
                    max={100}
                    className="progress-bar w-16 h-1.5"
                    data-variant={
                      prog.status === "done" ? "success" : "primary"
                    }
                    aria-label={`Scanning ${prog.name}`}
                  />
                  <span className="text-[10px] text-muted-foreground w-10 text-right">
                    {pct}%
                  </span>
                </div>
              );
            })()}
        </div>
        {n.expanded && (
          <div className="ml-4 border-l border-border/30 pl-1">
            {n.children.length > 0 && (
              <DirTree
                nodes={n.children}
                depth={depth + 1}
                treeFiles={treeFiles}
                toggleExpand={toggleExpand}
                toggleSelect={toggleSelect}
                scanning={scanning}
                dirProgress={dirProgress}
                getFileIcon={getFileIcon}
                openFile={openFile}
                formatBytes={formatBytes}
                removeFile={removeFile}
              />
            )}
            {treeFiles[n.path] && treeFiles[n.path].length > 0 && (
              <div className="mt-1">
                {treeFiles[n.path].slice(0, 50).map((f) => (
                  <div
                    key={f.path}
                    className="flex items-center gap-1.5 py-0.5 px-1 hover:bg-muted/10 rounded-sm"
                  >
                    <span className="w-3.5 h-3.5 shrink-0" />
                    {getFileIcon(f.name)}
                    <button
                      onClick={() => openFile(f)}
                      className="text-[11px] text-foreground/80 truncate text-left flex-1 hover:text-primary"
                      title="Open preview"
                    >
                      {f.name}
                    </button>
                    <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                      {f.size ? formatBytes(f.size) : ""}
                    </span>
                    {f.extension && (
                      <span className="text-[9px] px-1 py-0.5 bg-muted/50 rounded text-muted-foreground uppercase shrink-0">
                        {f.extension}
                      </span>
                    )}
                    <button
                      onClick={() => openFile(f)}
                      className="text-primary hover:text-primary/80"
                      title="Open preview"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(f.path);
                      }}
                      className="text-destructive hover:text-destructive/80"
                      title="Remove file"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
                {treeFiles[n.path].length > 50 && (
                  <div className="text-[10px] text-muted-foreground px-6 py-1">
                    ... and {treeFiles[n.path].length - 50} more files
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    ))}
  </div>
);

const LocalDirectorySelector: React.FC<LocalDirectorySelectorProps> = ({
  rootDirs,
  treeFiles,
  dirProgress,
  scanning,
  addDirectory,
  addFiles,
  removeDir,
  removeFile,
  onDragOver,
  onDragLeave,
  onDrop,
  dragActive,
  toggleExpand,
  toggleSelect,
  openFile,
  getFileIcon,
  formatBytes,
}) => (
  <div
    className={`bg-card border border-border rounded-sm p-4 space-y-3 transition-colors ${dragActive ? "ring-2 ring-primary/50 bg-primary/5" : ""}`}
    onDragOver={onDragOver}
    onDragEnter={onDragOver}
    onDragLeave={onDragLeave}
    onDrop={onDrop}
  >
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h3 className="text-[13px] font-semibold text-foreground">
          Select Directories or Files
        </h3>
        <p className="text-[11px] text-muted-foreground">
          Click folders to expand and explore. Toggle checkboxes to
          select/deselect.
        </p>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          Or drag and drop folders or files here to add them.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={addFiles}
          className="px-3 py-1.5 text-[12px] font-medium bg-secondary text-secondary-foreground rounded-sm hover:bg-secondary/80 transition-colors"
        >
          + Add Files
        </button>
        <button
          onClick={addDirectory}
          className="px-3 py-1.5 text-[12px] font-medium bg-primary text-primary-foreground rounded-sm hover:bg-primary/90 transition-colors"
        >
          + Add Directory
        </button>
      </div>
    </div>

    {rootDirs.length === 0 ? (
      <div className="border border-dashed border-border rounded-sm p-8 text-center">
        <HardDrive className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
        <p className="text-[12px] text-muted-foreground">
          No directories added yet.
        </p>
        <p className="text-[11px] text-muted-foreground mt-1">
          Click "Add Directory" to pick a drive or folder to explore.
        </p>
      </div>
    ) : (
      <div className="space-y-2">
        {rootDirs.map((dir) => (
          <div key={dir.path} className="border border-border rounded-sm p-2">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-primary" />
                <span className="text-[13px] font-semibold text-foreground">
                  {dir.name}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {dir.children.length} subfolder
                  {dir.children.length !== 1 ? "s" : ""}
                  {treeFiles[dir.path]
                    ? `, ${treeFiles[dir.path].length} files`
                    : ""}
                </span>
              </div>
              <button
                onClick={() => removeDir(dir.path)}
                className="text-muted-foreground hover:text-destructive"
                aria-label={`Remove ${dir.name}`}
                title={`Remove ${dir.name}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="max-h-[400px] overflow-y-auto space-y-2">
              {dir.children.length > 0 && (
                <DirTree
                  nodes={dir.children}
                  depth={1}
                  treeFiles={treeFiles}
                  toggleExpand={toggleExpand}
                  toggleSelect={toggleSelect}
                  scanning={scanning}
                  dirProgress={dirProgress}
                  getFileIcon={getFileIcon}
                  openFile={openFile}
                  formatBytes={formatBytes}
                  removeFile={removeFile}
                />
              )}
              {treeFiles[dir.path] && treeFiles[dir.path].length > 0 && (
                <div className="ml-4 border-l border-border/30 pl-1">
                  {treeFiles[dir.path].slice(0, 50).map((f) => (
                    <div
                      key={f.path}
                      className="flex items-center gap-1.5 py-0.5 px-1 hover:bg-muted/10 rounded-sm"
                    >
                      <span className="w-3.5 h-3.5 shrink-0" />
                      {getFileIcon(f.name)}
                      <button
                        onClick={() => openFile(f)}
                        className="text-[11px] text-foreground/80 truncate text-left flex-1 hover:text-primary"
                        title="Open preview"
                      >
                        {f.name}
                      </button>
                      <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                        {f.size ? formatBytes(f.size) : ""}
                      </span>
                      {f.extension && (
                        <span className="text-[9px] px-1 py-0.5 bg-muted/50 rounded text-muted-foreground uppercase shrink-0">
                          {f.extension}
                        </span>
                      )}
                      <button
                        onClick={() => openFile(f)}
                        className="text-primary hover:text-primary/80"
                        title="Open preview"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(f.path);
                        }}
                        className="text-destructive hover:text-destructive/80"
                        title="Remove file"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                  {treeFiles[dir.path].length > 50 && (
                    <div className="text-[10px] text-muted-foreground px-6 py-1">
                      ... and {treeFiles[dir.path].length - 50} more files
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

export default LocalDirectorySelector;
