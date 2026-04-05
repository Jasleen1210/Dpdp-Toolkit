import React, {
  useState,
  useCallback,
  useRef,
  useEffect,
  useMemo,
} from "react";
import {
  X,
  Loader2,
  FileText,
  Image,
  FileSpreadsheet,
  File,
  FileCode,
  FileArchive,
  Film,
  Music,
} from "lucide-react";
import { scanFiles as scanFilesAPI } from "../../../api/local";
import { buildScanPayloadEntry, extractTextForScan } from "./fileTextParsers";
import LocalDirectorySelector from "./LocalDirectorySelector";
import LocalScanResults from "./LocalScanResults";

export interface FileEntry {
  name: string;
  kind: "file" | "directory";
  path: string;
  size?: number;
  lastModified?: number;
  extension?: string;
  handle?: FileSystemFileHandle;
}

export interface DirNode {
  name: string;
  path: string;
  selected: boolean;
  expanded: boolean;
  children: DirNode[];
  loading: boolean;
  handle?: FileSystemDirectoryHandle;
}

export interface FileStats {
  total: number;
  byType: Record<
    string,
    { count: number; size: number; icon: React.ReactNode }
  >;
  totalSize: number;
}

export interface DirProgress {
  name: string;
  processed: number;
  total: number;
  status: "pending" | "scanning" | "done";
}

export interface FilePreview {
  name: string;
  path: string;
  content?: string;
  url?: string;
  mime?: string;
  kind: "text" | "image" | "pdf" | "unsupported";
}

export type FileCategories = typeof FILE_CATEGORIES;

export const FILE_CATEGORIES: Record<
  string,
  { label: string; extensions: string[]; icon: React.ReactNode }
> = {
  pdf: {
    label: "PDFs",
    extensions: [".pdf"],
    icon: <FileText className="w-4 h-4" />,
  },
  csv: {
    label: "CSVs / Spreadsheets",
    extensions: [".csv", ".xlsx", ".xls", ".tsv", ".ods"],
    icon: <FileSpreadsheet className="w-4 h-4" />,
  },
  images: {
    label: "Images",
    extensions: [
      ".jpg",
      ".jpeg",
      ".png",
      ".gif",
      ".svg",
      ".webp",
      ".bmp",
      ".ico",
      ".tiff",
    ],
    icon: <Image className="w-4 h-4" />,
  },
  documents: {
    label: "Documents",
    extensions: [".doc", ".docx", ".odt", ".rtf", ".txt", ".md"],
    icon: <FileText className="w-4 h-4" />,
  },
  code: {
    label: "Code Files",
    extensions: [
      ".js",
      ".ts",
      ".jsx",
      ".tsx",
      ".py",
      ".java",
      ".cpp",
      ".c",
      ".go",
      ".rs",
      ".html",
      ".css",
      ".scss",
      ".json",
      ".xml",
      ".yaml",
      ".yml",
      ".toml",
      ".sql",
      ".sh",
      ".bat",
      ".php",
      ".rb",
    ],
    icon: <FileCode className="w-4 h-4" />,
  },
  archives: {
    label: "Archives",
    extensions: [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    icon: <FileArchive className="w-4 h-4" />,
  },
  video: {
    label: "Videos",
    extensions: [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    icon: <Film className="w-4 h-4" />,
  },
  audio: {
    label: "Audio",
    extensions: [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    icon: <Music className="w-4 h-4" />,
  },
};

const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".next",
  ".cache",
  "coverage",
]);

const RELEVANT_EXT = new Set([
  "txt",
  "csv",
  "json",
  "md",
  "log",
  "pdf",
  "docx",
  "xlsx",
  "r",
]);

function categorizeFile(name: string): string {
  const ext = "." + name.split(".").pop()?.toLowerCase();
  for (const [cat, { extensions }] of Object.entries(FILE_CATEGORIES)) {
    if (extensions.includes(ext)) return cat;
  }
  return "other";
}

function recalcStats(files: FileEntry[]): FileStats | null {
  const byType: Record<
    string,
    { count: number; size: number; icon: React.ReactNode }
  > = {};
  let totalSize = 0;
  for (const f of files) {
    const cat = categorizeFile(f.name);
    if (!byType[cat]) {
      const catInfo = FILE_CATEGORIES[cat];
      byType[cat] = {
        count: 0,
        size: 0,
        icon: catInfo?.icon || <File className="w-4 h-4" />,
      };
    }
    byType[cat].count++;
    byType[cat].size += f.size || 0;
    totalSize += f.size || 0;
  }
  return files.length === 0 ? null : { total: files.length, byType, totalSize };
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export default function LocalFilesPanel() {
  const [rootDirs, setRootDirs] = useState<DirNode[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<FileEntry[]>([]);
  const [stats, setStats] = useState<FileStats | null>(null);
  const [scanProgress, setScanProgress] = useState("");
  const [treeFiles, setTreeFiles] = useState<Record<string, FileEntry[]>>({});
  const [dirProgress, setDirProgress] = useState<Record<string, DirProgress>>(
    {},
  );
  const [fileListLimit, setFileListLimit] = useState(100);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const [showSupportHelp, setShowSupportHelp] = useState(false);
  const [supportHelpNote, setSupportHelpNote] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const rootDirsRef = useRef<DirNode[]>([]);
  const dirProgressRef = useRef<Record<string, DirProgress>>({});
  const lastProgressUpdateRef = useRef(0);
  const bufferedCountRef = useRef(0);

  const filesByType = useMemo(() => {
    const map: Record<string, FileEntry[]> = {};
    for (const f of scannedFiles) {
      const cat = categorizeFile(f.name);
      if (!map[cat]) map[cat] = [];
      if (map[cat].length < 10) map[cat].push(f);
    }
    return map;
  }, [scannedFiles]);

  useEffect(() => {
    rootDirsRef.current = rootDirs;
  }, [rootDirs, treeFiles]);

  useEffect(() => {
    dirProgressRef.current = dirProgress;
  }, [dirProgress]);

  const supportsAPI =
    typeof window !== "undefined" && "showDirectoryPicker" in window;

  const handleOpenFlag = async (url: string) => {
    setSupportHelpNote("");
    try {
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) throw new Error("blocked");
      return;
    } catch {}

    try {
      await navigator.clipboard.writeText(url);
      setSupportHelpNote(
        "Browser blocked direct open. Link copied—paste into the address bar and press Enter.",
      );
    } catch {
      setSupportHelpNote(
        "Browser blocked direct open. Copy this link and paste into the address bar: " +
          url,
      );
    }
  };

  const loadChildren = useCallback(
    async (handle: FileSystemDirectoryHandle, parentPath: string) => {
      const dirs: DirNode[] = [];
      const files: FileEntry[] = [];
      try {
        for await (const entry of (handle as any).values()) {
          if (entry.kind === "directory") {
            if (SKIP_DIRS.has(entry.name)) continue;
            dirs.push({
              name: entry.name,
              path: parentPath + "/" + entry.name,
              selected: true,
              expanded: false,
              children: [],
              loading: false,
              handle: entry,
            });
          } else {
            const ext = entry.name.includes(".")
              ? entry.name.split(".").pop()?.toLowerCase()
              : undefined;
            const size = 0; // lazily fetched only when previewing
            files.push({
              name: entry.name,
              kind: "file",
              path: parentPath + "/" + entry.name,
              size,
              extension: ext,
              handle: entry,
            });
          }
        }
      } catch {}
      dirs.sort((a, b) => a.name.localeCompare(b.name));
      files.sort((a, b) => a.name.localeCompare(b.name));
      return { dirs, files };
    },
    [],
  );

  const addFileHandles = useCallback((handles: FileSystemFileHandle[]) => {
    if (!handles || handles.length === 0) return;

    const parentPath = "/Selected Files";
    const files: FileEntry[] = handles.map((handle) => {
      const name = handle.name;
      const ext = name.includes(".")
        ? name.split(".").pop()?.toLowerCase()
        : undefined;
      return {
        name,
        kind: "file",
        path: `${parentPath}/${name}`,
        size: 0,
        extension: ext,
        handle,
      };
    });

    setTreeFiles((prev) => {
      const existing = prev[parentPath] || [];
      const dedup = new Map<string, FileEntry>();
      [...existing, ...files].forEach((f) => dedup.set(f.path, f));
      return { ...prev, [parentPath]: Array.from(dedup.values()) };
    });

    setRootDirs((prev) => {
      const exists = prev.some((d) => d.path === parentPath);
      if (exists) return prev;
      const newDir: DirNode = {
        name: "Selected Files",
        path: parentPath,
        selected: true,
        expanded: true,
        children: [],
        loading: false,
      };
      return [...prev, newDir];
    });
  }, []);

  const addFiles = useCallback(async () => {
    try {
      const handles: FileSystemFileHandle[] = await (
        window as any
      ).showOpenFilePicker({ multiple: true });
      addFileHandles(handles);
    } catch {}
  }, [addFileHandles]);

  const importDirectoryHandle = useCallback(
    async (dirHandle: FileSystemDirectoryHandle) => {
      const parentPath = "/" + dirHandle.name;
      const exists = rootDirsRef.current.some((d) => d.path === parentPath);
      if (exists) return;

      try {
        const { dirs, files } = await loadChildren(dirHandle, parentPath);
        const newDir: DirNode = {
          name: dirHandle.name,
          path: parentPath,
          selected: true,
          expanded: true,
          children: dirs,
          loading: false,
          handle: dirHandle,
        };

        setRootDirs((prev) => [...prev, newDir]);
        setTreeFiles((prev) => ({ ...prev, [parentPath]: files }));
      } catch {}
    },
    [loadChildren],
  );

  const addDirectory = useCallback(async () => {
    try {
      const dirHandle = await (window as any).showDirectoryPicker({
        mode: "read",
      });
      await importDirectoryHandle(dirHandle);
    } catch {}
  }, [importDirectoryHandle]);

  const handleDropItems = useCallback(
    async (items: DataTransferItemList) => {
      if (!items || items.length === 0) return;

      const fileHandles: FileSystemFileHandle[] = [];
      const dirHandles: FileSystemDirectoryHandle[] = [];

      for (const item of Array.from(items)) {
        try {
          const handle = await (item as any).getAsFileSystemHandle?.();
          if (!handle) continue;
          if (handle.kind === "directory")
            dirHandles.push(handle as FileSystemDirectoryHandle);
          else if (handle.kind === "file")
            fileHandles.push(handle as FileSystemFileHandle);
        } catch {}
      }

      for (const dirHandle of dirHandles) {
        await importDirectoryHandle(dirHandle);
      }

      if (fileHandles.length > 0) addFileHandles(fileHandles);
    },
    [addFileHandles, importDirectoryHandle],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (!supportsAPI) return;
      const items = e.dataTransfer?.items;
      if (items && items.length > 0) await handleDropItems(items);
    },
    [handleDropItems, supportsAPI],
  );

  const toggleExpand = useCallback(
    async (path: string) => {
      const inferProgressChildren = (parentPath: string): DirNode[] => {
        const inferred: Record<string, DirNode> = {};
        const progress = dirProgressRef.current;
        const prefix = parentPath.endsWith("/") ? parentPath : parentPath + "/";

        for (const key of Object.keys(progress)) {
          if (!key.startsWith(prefix)) continue;
          const remainder = key.slice(prefix.length);
          if (!remainder || remainder.includes("/")) continue;
          const name = remainder;
          if (inferred[key]) continue;
          inferred[key] = {
            name,
            path: key,
            selected: true,
            expanded: false,
            children: [],
            loading: false,
          };
        }

        return Object.values(inferred).sort((a, b) =>
          a.name.localeCompare(b.name),
        );
      };

      const mergeChildren = (existing: DirNode[], inferred: DirNode[]) => {
        const byPath = new Map<string, DirNode>();
        for (const c of existing) byPath.set(c.path, c);
        for (const c of inferred)
          if (!byPath.has(c.path)) byPath.set(c.path, c);
        return Array.from(byPath.values()).sort((a, b) =>
          a.name.localeCompare(b.name),
        );
      };

      const findNode = (nodes: DirNode[]): DirNode | null => {
        for (const n of nodes) {
          if (n.path === path) return n;
          const found = findNode(n.children);
          if (found) return found;
        }
        return null;
      };

      const target = findNode(rootDirsRef.current);
      if (!target) return;
      const newExpanded = !target.expanded;
      const needsLoad =
        newExpanded && target.children.length === 0 && !!target.handle;
      const inferredChildren = newExpanded ? inferProgressChildren(path) : [];

      const toggleExpanded = (nodes: DirNode[]): DirNode[] =>
        nodes.map((n) => {
          if (n.path === path)
            return {
              ...n,
              expanded: newExpanded,
              loading: needsLoad,
              children: mergeChildren(n.children, inferredChildren),
            };
          return { ...n, children: toggleExpanded(n.children) };
        });

      setRootDirs((prev) => toggleExpanded(prev));

      if (needsLoad && target.handle) {
        const { dirs, files } = await loadChildren(target.handle, target.path);
        setTreeFiles((prev) => ({ ...prev, [target.path]: files }));

        const attachChildren = (nodes: DirNode[]): DirNode[] =>
          nodes.map((n) => {
            if (n.path === path)
              return {
                ...n,
                children: mergeChildren(dirs, inferProgressChildren(path)),
                loading: false,
                expanded: newExpanded,
              };
            return { ...n, children: attachChildren(n.children) };
          });

        setRootDirs((prev) => attachChildren(prev));
      }
    },
    [loadChildren],
  );

  const toggleSelect = useCallback((path: string) => {
    setRootDirs((prev) => {
      const update = (nodes: DirNode[]): DirNode[] =>
        nodes.map((n) => {
          if (n.path === path) {
            const newSelected = !n.selected;
            const selectAll = (node: DirNode): DirNode => ({
              ...node,
              selected: newSelected,
              children: node.children.map(selectAll),
            });
            return selectAll(n);
          }
          return { ...n, children: update(n.children) };
        });
      return update(prev);
    });
  }, []);

  const removeDir = useCallback(
    (path: string) => {
      const nextRoots = rootDirsRef.current.filter((d) => d.path !== path);
      const allowedRoots = nextRoots.map((d) => d.path);
      const isAllowed = (p: string) =>
        allowedRoots.some((root) => p.startsWith(root));

      const filteredFiles = scannedFiles.filter((f) => isAllowed(f.path));

      setRootDirs(nextRoots);
      setScannedFiles(filteredFiles);

      setPiiResults((prevPii: any[]) => {
        if (nextRoots.length === 0) return [];
        const names = new Set(filteredFiles.map((f) => f.name));
        return prevPii.filter((r: any) => names.has(r.file));
      });

      if (nextRoots.length === 0) {
        setStats(null);
        setDirProgress({});
        setScanProgress("");
      } else {
        setStats(recalcStats(filteredFiles));
      }

      setTreeFiles((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          if (key.startsWith(path)) delete next[key];
        }
        return next;
      });
    },
    [scannedFiles],
  );

  const removeFile = useCallback((path: string) => {
    const dirPath = path.includes("/")
      ? path.slice(0, path.lastIndexOf("/"))
      : "";

    setTreeFiles((prev) => {
      const next = { ...prev };
      const list = next[dirPath];
      if (list) {
        const filtered = list.filter((f) => f.path !== path);
        if (filtered.length === 0) delete next[dirPath];
        else next[dirPath] = filtered;
      }
      return next;
    });

    setScannedFiles((prev) => {
      const next = prev.filter((f) => f.path !== path);
      setStats(recalcStats(next));
      return next;
    });

    setPiiResults((prevPii: any[]) => {
      const fileName = path.split("/").pop();
      return prevPii.filter((r: any) => r.file !== fileName);
    });
  }, []);
  const [piiResults, setPiiResults] = useState<any[]>([]);
  const scanFiles = useCallback(async () => {
    const prevFiles = scannedFiles;
    const prevMap = new Map(prevFiles.map((f) => [f.path, f]));
    const allowedRoots = rootDirs.map((d) => d.path);
    const isAllowed = (p: string) =>
      allowedRoots.some((root) => p.startsWith(root));

    setScanning(true);
    setScannedFiles([]);
    setStats(null);

    setDirProgress({});
    setFileListLimit(100);
    lastProgressUpdateRef.current = 0;
    bufferedCountRef.current = 0;
    const allFiles: FileEntry[] = [];
    const seenPaths = new Set<string>();
    try {
      const bumpProgress = (
        key: string,
        name: string,
        deltaProcessed = 0,
        deltaTotal = 0,
        forceStatus?: DirProgress["status"],
      ) => {
        setDirProgress((prev) => {
          const current = prev[key] || {
            name,
            processed: 0,
            total: 1,
            status: "pending" as const,
          };
          const nextTotal = Math.max(1, current.total + deltaTotal);
          const nextProcessed = Math.max(0, current.processed + deltaProcessed);
          const status =
            forceStatus || (nextProcessed >= nextTotal ? "done" : "scanning");
          return {
            ...prev,
            [key]: {
              ...current,
              processed: nextProcessed,
              total: nextTotal,
              status,
            },
          };
        });
      };

      const tryAddFile = (
        file: FileEntry,
        progressKey?: string,
        label?: string,
      ) => {
        if (seenPaths.has(file.path)) return;
        seenPaths.add(file.path);
        allFiles.push(file);
        bufferedCountRef.current += 1;
        const now = Date.now();
        if (
          bufferedCountRef.current >= 500 ||
          now - lastProgressUpdateRef.current > 200
        ) {
          setScanProgress(
            `Scanning... ${allFiles.length.toLocaleString()} files found`,
          );
          bufferedCountRef.current = 0;
          lastProgressUpdateRef.current = now;
        }
        if (progressKey && label) bumpProgress(progressKey, label, 1, 0);
      };

      const queue: Array<() => Promise<void>> = [];
      const CONCURRENCY = 30;

      const runQueue = async () => {
        const workers = Array.from({ length: CONCURRENCY }, async () => {
          while (queue.length > 0) {
            const job = queue.shift();
            if (!job) break;
            await job();
          }
        });
        await Promise.all(workers);
      };

      const scanDir = async (
        handle: FileSystemDirectoryHandle,
        basePath: string,
        progressKey: string,
        label: string,
        depth: number,
      ) => {
        if (depth > 8) return;
        bumpProgress(progressKey, label, 0, 0, "scanning");

        try {
          const entries: any[] = [];
          for await (const entry of (handle as any).values())
            entries.push(entry);
          bumpProgress(progressKey, label, 0, entries.length);

          const processEntries = entries.map(async (entry) => {
            if (entry.kind === "file") {
              const ext = entry.name.includes(".")
                ? entry.name.split(".").pop()?.toLowerCase()
                : undefined;
              if (!ext || !RELEVANT_EXT.has(ext)) {
                bumpProgress(progressKey, label, 1, 0);
                return;
              }

              try {
                tryAddFile(
                  {
                    name: entry.name,
                    kind: "file",
                    path: basePath + "/" + entry.name,
                    size: 0,
                    lastModified: undefined,
                    extension: ext,
                    handle: entry,
                  },
                  progressKey,
                  label,
                );
              } catch {}
            } else if (entry.kind === "directory") {
              if (SKIP_DIRS.has(entry.name)) {
                bumpProgress(progressKey, label, 1, 0);
                return;
              }

              const childPath = basePath + "/" + entry.name;
              bumpProgress(progressKey, label, 0, 1);
              bumpProgress(childPath, entry.name, 0, 1, "pending");
              queue.push(async () => {
                await scanDir(
                  entry,
                  childPath,
                  childPath,
                  entry.name,
                  depth + 1,
                );
                bumpProgress(progressKey, label, 1, 0);
                bumpProgress(childPath, entry.name, 1, 0, "done");
              });
            }
          });

          await Promise.all(processEntries);
        } catch {}
      };

      for (const dir of rootDirs) {
        if (!dir.selected) continue;

        if (!dir.handle) {
          const files = treeFiles[dir.path] || [];
          if (files.length > 0) {
            setScanProgress(
              `Including ${files.length} selected file${files.length === 1 ? "" : "s"}...`,
            );
            for (const f of files) {
              if (f.extension && !RELEVANT_EXT.has(f.extension)) continue;
              tryAddFile(f);
            }
          }
          continue;
        }

        if (dir.selected && dir.handle) {
          setScanProgress(`Scanning ${dir.name}...`);
          bumpProgress(dir.path, dir.name, 0, 0, "scanning");

          const entries: any[] = [];
          try {
            for await (const entry of (dir.handle as any).values())
              entries.push(entry);
          } catch {}

          const preloaded = treeFiles[dir.path] || [];
          if (preloaded.length > 0) {
            setScanProgress(
              `Including ${preloaded.length} file${preloaded.length === 1 ? "" : "s"} at root...`,
            );
            for (const f of preloaded) {
              if (f.extension && !RELEVANT_EXT.has(f.extension)) continue;
              tryAddFile(f, dir.path, dir.name);
            }
          }

          await Promise.all(
            entries.map(async (entry) => {
              if (entry.kind === "file") {
                const ext = entry.name.includes(".")
                  ? entry.name.split(".").pop()?.toLowerCase()
                  : undefined;
                if (!ext || !RELEVANT_EXT.has(ext)) {
                  bumpProgress(dir.path, dir.name, 1, 0);
                  return;
                }

                try {
                  tryAddFile(
                    {
                      name: entry.name,
                      kind: "file",
                      path: dir.path + "/" + entry.name,
                      size: 0,
                      lastModified: undefined,
                      extension: ext,
                      handle: entry,
                    },
                    dir.path,
                    dir.name,
                  );
                } catch {}
              } else if (entry.kind === "directory") {
                if (SKIP_DIRS.has(entry.name)) {
                  bumpProgress(dir.path, dir.name, 1, 0);
                  return;
                }

                const childPath = dir.path + "/" + entry.name;
                bumpProgress(dir.path, dir.name, 0, 1);
                bumpProgress(childPath, entry.name, 0, 1, "pending");
                queue.push(async () => {
                  await scanDir(entry, childPath, childPath, entry.name, 0);
                  bumpProgress(dir.path, dir.name, 1, 0);
                  bumpProgress(childPath, entry.name, 1, 0, "done");
                });
              }
            }),
          );

          if (entries.length > 0)
            bumpProgress(dir.path, dir.name, 0, entries.length);
        }
      }

      await runQueue();

      const prevPiiMap = new Map<string, any>(
        piiResults.map((r: any) => [r.file, r]),
      );

      // determine new/kept files and merge with prior scans for active roots
      const currentMap = new Map(allFiles.map((f) => [f.path, f]));

      const newFiles = allFiles.filter((f) => !prevMap.has(f.path));
      const filesNeedingScan = allFiles.filter((f) => !prevPiiMap.has(f.name));

      // start with previously scanned files still under active roots
      const mergedMap = new Map<string, FileEntry>();
      for (const [path, prev] of prevMap) {
        if (!isAllowed(path)) continue;
        mergedMap.set(path, { ...prev });
      }

      // overlay current scan results (updates/additions)
      for (const [path, f] of currentMap) {
        mergedMap.set(path, { ...mergedMap.get(path), ...f });
      }

      const keptFiles = Array.from(mergedMap.values());

      // enrich metadata only for files that still need PII results
      const filesToSend = [];
      for (const f of filesNeedingScan) {
        if (!f.handle) continue;
        try {
          const blob = await f.handle.getFile();
          f.size = blob.size;

          const payloadEntry = await buildScanPayloadEntry({
            name: f.name,
            extension: f.extension,
            blob,
          });

          if (payloadEntry) filesToSend.push(payloadEntry);
        } catch (err) {
          console.error("Failed to parse file for scan payload:", f.name, err);
        }
      }

      const mergedFiles = Array.from(
        new Map([...keptFiles, ...newFiles].map((f) => [f.path, f])).values(),
      ).filter((f) => isAllowed(f.path));

      const byType: Record<
        string,
        { count: number; size: number; icon: React.ReactNode }
      > = {};
      let totalSize = 0;
      for (const f of mergedFiles) {
        const cat = categorizeFile(f.name);
        if (!byType[cat]) {
          const catInfo = FILE_CATEGORIES[cat];
          byType[cat] = {
            count: 0,
            size: 0,
            icon: catInfo?.icon || <File className="w-4 h-4" />,
          };
        }
        byType[cat].count++;
        byType[cat].size += f.size || 0;
        totalSize += f.size || 0;
      }

      setScannedFiles(mergedFiles);

      // Call API only with new files
      console.log("[LocalScan] Prepared payload entries", {
        count: filesToSend.length,
        names: filesToSend.map((f) => f.name),
        sample: filesToSend.slice(0, 2).map((f) => ({
          name: f.name,
          chars: f.content.length,
          preview: f.content.slice(0, 200),
        })),
      });

      const data = await scanFilesAPI(filesToSend);
      console.log("PII RESULTS:", data);

      const newPiiMap = new Map<string, any>(
        (data.results || []).map((r: any) => [r.file, r]),
      );

      // merge previous PII results for kept files, overwrite with new when present
      const mergedPii: any[] = [];
      for (const f of mergedFiles) {
        const res = newPiiMap.get(f.name) || prevPiiMap.get(f.name);
        if (res) mergedPii.push(res);
      }
      setPiiResults(mergedPii);

      setStats({ total: mergedFiles.length, byType, totalSize });
      setFileListLimit(Math.min(100, mergedFiles.length));
    } catch {
    } finally {
      setScanning(false);
      setScanProgress("");
    }
  }, [rootDirs, scannedFiles, treeFiles, piiResults]);

  const getFileIcon = (name: string) => {
    const cat = categorizeFile(name);
    const catInfo = FILE_CATEGORIES[cat];
    if (catInfo) return <span className="text-primary/60">{catInfo.icon}</span>;
    return <File className="w-3.5 h-3.5 text-muted-foreground" />;
  };

  const closePreview = useCallback(() => {
    setPreview((prev) => {
      if (prev?.url) URL.revokeObjectURL(prev.url);
      return null;
    });
    setPreviewError("");
    setPreviewLoading(false);
  }, []);

  const openFile = useCallback(
    async (file: FileEntry) => {
      closePreview();
      setPreviewLoading(true);
      try {
        if (!file.handle)
          throw new Error("File handle not available for preview");

        const blob = await file.handle.getFile();
        const mime = blob.type;
        const isImage = mime.startsWith("image/");
        const isPdf =
          mime === "application/pdf" ||
          file.name.toLowerCase().endsWith(".pdf");
        const isDocx =
          mime ===
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
          file.name.toLowerCase().endsWith(".docx");

        if (isImage) {
          const url = URL.createObjectURL(blob);
          setPreview({
            name: file.name,
            path: file.path,
            url,
            mime,
            kind: "image",
          });
        } else if (isPdf) {
          const url = URL.createObjectURL(blob);
          setPreview({
            name: file.name,
            path: file.path,
            url,
            mime,
            kind: "pdf",
          });
        } else if (isDocx) {
          const content = await extractTextForScan({
            name: file.name,
            extension: file.extension,
            blob,
          });
          setPreview({
            name: file.name,
            path: file.path,
            content: content || "[No extractable text found in document]",
            mime,
            kind: "text",
          });
        } else {
          const LIMIT = 300000; // ~300 KB for quick text previews
          const truncated = blob.size > LIMIT;
          const content = await blob.slice(0, LIMIT).text();
          const suffix = truncated ? "\n\n...[truncated preview]" : "";
          setPreview({
            name: file.name,
            path: file.path,
            content: content + suffix,
            mime,
            kind: "text",
          });
        }
        setPreviewError("");
      } catch (err: any) {
        setPreviewError(err?.message || "Unable to open file");
        setPreview({ name: file.name, path: file.path, kind: "unsupported" });
      } finally {
        setPreviewLoading(false);
      }
    },
    [closePreview],
  );

  if (!supportsAPI) {
    return (
      <>
        <div className="bg-card border border-border rounded-sm p-6 text-center space-y-2">
          <p className="text-[13px] text-destructive font-medium">
            File System Access API not supported
          </p>
          <p className="text-[12px] text-muted-foreground">
            Please use Chrome, Edge, or Opera to access local file scanning.
          </p>
          <p className="text-[11px] text-muted-foreground">
            When prompted by the browser, allow the picker popup and grant
            folder access so scanning can proceed.
          </p>
          <button
            onClick={() => setShowSupportHelp(true)}
            className="mt-3 px-3 py-1.5 text-[12px] font-semibold bg-primary text-primary-foreground rounded-sm hover:bg-primary/90"
          >
            View setup steps per browser
          </button>
        </div>

        {showSupportHelp && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-card border border-border rounded-sm shadow-lg w-full max-w-xl">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <h3 className="text-[13px] font-semibold text-foreground">
                  Enable local file access
                </h3>
                <button
                  onClick={() => setShowSupportHelp(false)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Close support dialog"
                  title="Close support dialog"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="p-4 space-y-3 text-[12px] text-foreground">
                <p className="text-muted-foreground">
                  Open the relevant flags/settings page in a new tab, enable the
                  File System Access API if required, then restart the browser.
                </p>
                {supportHelpNote && (
                  <div className="text-[11px] text-foreground bg-muted/50 border border-border rounded-sm px-3 py-2">
                    {supportHelpNote}
                  </div>
                )}
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2 border border-border rounded-sm px-3 py-2">
                    <div>
                      <div className="font-semibold">Brave</div>
                      <div className="text-muted-foreground text-[11px]">
                        Enable File System Access API flag, then restart Brave.
                      </div>
                    </div>
                    <button
                      onClick={() =>
                        handleOpenFlag("brave://flags/#file-system-access-api")
                      }
                      className="text-primary hover:text-primary/80 text-[11px] font-semibold"
                    >
                      Open flag
                    </button>
                  </div>

                  <div className="flex items-center justify-between gap-2 border border-border rounded-sm px-3 py-2">
                    <div>
                      <div className="font-semibold">Chrome</div>
                      <div className="text-muted-foreground text-[11px]">
                        Supported by default; if disabled, check the flag below.
                      </div>
                    </div>
                    <button
                      onClick={() =>
                        handleOpenFlag("chrome://flags/#file-system-access-api")
                      }
                      className="text-primary hover:text-primary/80 text-[11px] font-semibold"
                    >
                      Open flag
                    </button>
                  </div>

                  <div className="flex items-center justify-between gap-2 border border-border rounded-sm px-3 py-2">
                    <div>
                      <div className="font-semibold">Edge</div>
                      <div className="text-muted-foreground text-[11px]">
                        Supported by default; if disabled, use the flag page.
                      </div>
                    </div>
                    <button
                      onClick={() =>
                        handleOpenFlag("edge://flags/#file-system-access-api")
                      }
                      className="text-primary hover:text-primary/80 text-[11px] font-semibold"
                    >
                      Open flag
                    </button>
                  </div>

                  <div className="flex items-center justify-between gap-2 border border-border rounded-sm px-3 py-2">
                    <div>
                      <div className="font-semibold">Firefox</div>
                      <div className="text-muted-foreground text-[11px]">
                        Not supported; use a Chromium-based browser for this
                        feature.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <LocalDirectorySelector
        rootDirs={rootDirs}
        treeFiles={treeFiles}
        dirProgress={dirProgress}
        scanning={scanning}
        addDirectory={addDirectory}
        addFiles={addFiles}
        removeDir={removeDir}
        removeFile={removeFile}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        dragActive={dragActive}
        toggleExpand={toggleExpand}
        toggleSelect={toggleSelect}
        openFile={openFile}
        getFileIcon={getFileIcon}
        formatBytes={formatBytes}
      />

      {rootDirs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <button
              onClick={scanFiles}
              disabled={scanning}
              className="px-4 py-2 text-[12px] font-semibold bg-primary text-primary-foreground rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {scanning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {scanning ? "Scanning..." : "Deep Scan Selected Directories"}
            </button>
            {scanProgress && (
              <span className="text-[11px] text-muted-foreground animate-pulse">
                {scanProgress}
              </span>
            )}
          </div>
        </div>
      )}

      {stats && (
        <LocalScanResults
          stats={stats}
          fileCategories={FILE_CATEGORIES}
          filesByType={filesByType}
          getFileIcon={getFileIcon}
          openCategory={openCategory}
          setOpenCategory={setOpenCategory}
          scannedFiles={scannedFiles}
          fileListLimit={fileListLimit}
          setFileListLimit={setFileListLimit}
          openFile={openFile}
          piiResults={piiResults}
          rootDirs={rootDirs}
          formatBytes={formatBytes}
        />
      )}

      {(previewLoading || preview || previewError) && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-sm shadow-lg w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div>
                <div className="text-[13px] font-semibold text-foreground">
                  {preview?.name || "Preview"}
                </div>
                <div className="text-[11px] text-muted-foreground truncate max-w-[500px]">
                  {preview?.path ||
                    (previewError ? "Error opening file" : "Loading file...")}
                </div>
              </div>
              <button
                onClick={closePreview}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Close preview"
                title="Close preview"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 overflow-auto text-[12px] bg-background/60 flex-1">
              {previewLoading && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading...
                </div>
              )}
              {!previewLoading && previewError && (
                <div className="text-destructive text-[12px]">
                  {previewError}
                </div>
              )}
              {!previewLoading && preview && (
                <div className="border border-border rounded-sm bg-card/60 p-3 h-full">
                  {preview.kind === "image" && preview.url && (
                    <div className="flex justify-center">
                      <img
                        src={preview.url}
                        alt={preview.name}
                        className="max-h-[60vh] object-contain"
                      />
                    </div>
                  )}
                  {preview.kind === "pdf" && preview.url && (
                    <div className="h-[60vh]">
                      <iframe
                        src={preview.url}
                        title={preview.name}
                        className="w-full h-full border border-border rounded-sm"
                      />
                    </div>
                  )}
                  {preview.kind === "text" && preview.content && (
                    <pre className="text-[12px] whitespace-pre-wrap break-words font-mono">
                      {preview.content}
                    </pre>
                  )}
                  {preview.kind === "unsupported" && !previewError && (
                    <div className="text-muted-foreground">
                      Preview not available for this file type.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
