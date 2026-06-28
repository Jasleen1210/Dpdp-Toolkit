package scanner

import (
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"dpdp-toolkit/agent-go/internal/config"
	"dpdp-toolkit/agent-go/internal/pii"
	"dpdp-toolkit/agent-go/internal/types"
)

type Engine struct {
	cfg config.Config
}

const (
	scanProgressLogEveryFiles = 250
	scanProgressLogEveryTime  = 10 * time.Second
)

type scanProgress struct {
	mode         string
	start        time.Time
	lastLogAt    time.Time
	lastScanned  int
	lastHitFiles int
	lastValues   int

	scannedFiles int
	hitFiles     int
	valuesFound  int
}

func newScanProgress(mode string, roots []string) *scanProgress {
	now := time.Now()
	p := &scanProgress{mode: mode, start: now, lastLogAt: now}
	log.Printf("%s scan started: roots=%d", mode, len(roots))
	return p
}

func (p *scanProgress) addScannedFile() {
	p.scannedFiles++
	p.maybeLog(false)
}

func (p *scanProgress) addHit(valuesInFile int) {
	p.hitFiles++
	p.valuesFound += valuesInFile
	p.maybeLog(false)
}

func (p *scanProgress) maybeLog(force bool) {
	if !force {
		if p.scannedFiles-p.lastScanned < scanProgressLogEveryFiles && time.Since(p.lastLogAt) < scanProgressLogEveryTime {
			return
		}
	}
	elapsed := time.Since(p.start).Round(time.Second)
	log.Printf(
		"%s scan progress: scanned_files=%d files_with_values=%d values_found=%d elapsed=%s",
		p.mode,
		p.scannedFiles,
		p.hitFiles,
		p.valuesFound,
		elapsed,
	)
	p.lastScanned = p.scannedFiles
	p.lastHitFiles = p.hitFiles
	p.lastValues = p.valuesFound
	p.lastLogAt = time.Now()
}

func (p *scanProgress) finish() {
	p.maybeLog(true)
}

func New(cfg config.Config) *Engine {
	return &Engine{cfg: cfg}
}

func (e *Engine) ScanTask(task types.Task) ([]types.Match, int) {
	roots := normalizedRoots(e.cfg.ScanPaths)

	if task.Type == "access" && strings.TrimSpace(task.Query) != "" {
		q := strings.TrimSpace(task.Query)
		if !strings.Contains(q, "::") && (strings.Contains(q, "/") || strings.Contains(q, "\\")) {
			roots = normalizedRoots([]string{q})
		}
	}

	targetQuery := strings.TrimSpace(task.Query)
	if task.Type == "update" || task.Type == "delete" {
		parts := strings.Split(task.Query, "::")
		targetQuery = strings.TrimSpace(parts[0])
	}

	queryLower := strings.ToLower(targetQuery)
	log.Printf("[ENGINE] Scanning roots %v for term: %q", roots, targetQuery)

	allMatches, scannedFiles := e.scanRootsForQuery(roots, queryLower, targetQuery)

	// Remove the masking-broken filter entirely for access/remediation tasks
	// scanRootsForQuery already only returns files that contain the query term
	return allMatches, scannedFiles
}

func (e *Engine) ScanPII(modifiedSince time.Time) ([]types.Match, int) {
	roots := normalizedRoots(e.cfg.ScanPaths)
	allMatches, scannedFiles := e.scanRootsForPII(roots, modifiedSince)

	return allMatches, scannedFiles
}

func (e *Engine) scanRootsForQuery(roots []string, query string, originalQuery string) ([]types.Match, int) {
	allMatches := make([]types.Match, 0)
	scannedFiles := 0
	progress := newScanProgress("task", roots)
	hitFiles := map[string]struct{}{}

	for idx, root := range roots {
		log.Printf("task scan root start: root=%s (%d/%d)", root, idx+1, len(roots))
		walkErr := filepath.WalkDir(root, func(filePath string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				if shouldSkipDir(d.Name()) {
					return filepath.SkipDir
				}
				return nil
			}

			// log.Printf("DEBUG: Checking file extension for path: %s", filePath) // <-- Add this
			if !e.isAllowedExtension(filePath) {
				// log.Printf("DEBUG: File skipped because extension is not allowed: %s", filePath) // <-- Add this
				return nil
			}

			scannedFiles++
			progress.addScannedFile()

			content, ok := extractText(filePath, e.cfg.MaxFileSizeMB*1024*1024)
			if !ok {
				return nil
			}

			lower := strings.ToLower(content)
			queryHit := query != "" && strings.Contains(lower, query)
			piiHits := pii.Detect(content, 10)

			if !queryHit && len(piiHits) == 0 {
				return nil
			}

			if _, seen := hitFiles[filePath]; !seen {
				hitFiles[filePath] = struct{}{}
				valuesInFile := len(piiHits)
				if valuesInFile == 0 && queryHit {
					valuesInFile = 1
				}
				progress.addHit(valuesInFile)
			}

			// Always add a QUERY_HIT match when the query term is found,
			// regardless of whether PII was also found
			if queryHit {
				allMatches = append(allMatches, types.Match{
					Type:  "QUERY_HIT",
					Value: originalQuery,
					File:  filePath,
				})
			}

			// Also add PII hits separately
			// for _, p := range piiHits {
			// 	allMatches = append(allMatches, types.Match{
			// 		Type:  p.Type,
			// 		Value: p.Value,
			// 		File:  filePath,
			// 	})
			// }

			// if queryHit && len(piiHits) == 0 {
			// 	allMatches = append(allMatches, types.Match{
			// 		Type:  "QUERY_HIT",
			// 		Value: originalQuery,
			// 		File:  filePath,
			// 	})
			// }

			return nil
		})

		if walkErr != nil {
			log.Printf("scan root skipped: root=%s error=%v", root, walkErr)
		}
		log.Printf("task scan root complete: root=%s scanned_files=%d files_with_values=%d", root, scannedFiles, len(hitFiles))
	}

	progress.finish()
	return allMatches, scannedFiles
}

func (e *Engine) scanRootsForPII(roots []string, modifiedSince time.Time) ([]types.Match, int) {
	allMatches := make([]types.Match, 0)
	scannedFiles := 0
	progress := newScanProgress("standalone", roots)
	hitFiles := map[string]struct{}{}

	for idx, root := range roots {
		log.Printf("standalone scan root start: root=%s (%d/%d)", root, idx+1, len(roots))
		walkErr := filepath.WalkDir(root, func(filePath string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				if shouldSkipDir(d.Name()) {
					return filepath.SkipDir
				}
				return nil
			}

			if !e.isAllowedExtension(filePath) {
				return nil
			}

			if !modifiedSince.IsZero() {
				info, err := d.Info()
				if err != nil {
					return nil
				}
				if info.ModTime().Before(modifiedSince) {
					return nil
				}
			}

			scannedFiles++
			progress.addScannedFile()

			// Find this block inside scanRootsForPII in internal/scanner/scanner.go:

			content, ok := extractText(filePath, e.cfg.MaxFileSizeMB*1024*1024)
			if !ok {
				log.Printf("DEBUG SCANNER: extractText failed for %s", filePath) // Add this line
				return nil
			}

			// ADD THIS TEMPORARY DEBUG BLOCK HERE:
			if len(content) > 100 {
				log.Printf("DEBUG SCANNER: Read file %s successfully. First 60 chars: %q", filePath, content[:60])
			} else {
				log.Printf("DEBUG SCANNER: Read file %s successfully. Full content: %q", filePath, content)
			}

			piiHits := pii.Detect(content, 10)

			if len(piiHits) == 0 {
				return nil
			}

			if _, seen := hitFiles[filePath]; !seen {
				hitFiles[filePath] = struct{}{}
				progress.addHit(len(piiHits))
			}

			for _, p := range piiHits {
				allMatches = append(allMatches, types.Match{
					Type:  p.Type,
					Value: p.Value,
					File:  filePath,
				})
			}

			return nil
		})

		if walkErr != nil {
			log.Printf("scan root skipped: root=%s error=%v", root, walkErr)
		}
		log.Printf("standalone scan root complete: root=%s scanned_files=%d files_with_values=%d", root, scannedFiles, len(hitFiles))
	}

	progress.finish()
	return allMatches, scannedFiles
}

func normalizedRoots(paths []string) []string {
	roots := make([]string, 0, len(paths))
	seen := map[string]struct{}{}

	for _, p := range paths {
		v := strings.TrimSpace(strings.Trim(p, `"'`))
		if v == "" {
			continue
		}
		v = filepath.Clean(v)
		if _, ok := seen[v]; ok {
			continue
		}
		seen[v] = struct{}{}
		roots = append(roots, v)
	}

	return roots
}

func (e *Engine) isAllowedExtension(filePath string) bool {
	if _, all := e.cfg.IncludeExts["*"]; all {
		return true
	}

	// e.g., "d:\mock_s3\data.txt" -> ".txt"
	extWithDot := strings.ToLower(filepath.Ext(filePath))

	// 1. Try matching with the dot (e.g., ".txt")
	if _, ok := e.cfg.IncludeExts[extWithDot]; ok {
		return true
	}

	// 2. Try matching without the dot (e.g., "txt")
	extWithoutDot := strings.TrimPrefix(extWithDot, ".")
	_, ok := e.cfg.IncludeExts[extWithoutDot]
	return ok
}

func shouldSkipDir(name string) bool {
	n := strings.ToLower(name)
	// Dirs to skip on all platforms
	switch n {
	case ".git", "node_modules":
		return true
	}
	// Windows-only dirs
	if runtime.GOOS == "windows" {
		switch n {
		case "appdata", "$recycle.bin", "windows",
			"program files", "program files (x86)":
			return true
		}
	}
	// macOS-only dirs
	if runtime.GOOS == "darwin" {
		switch n {
		case "library", ".trash", "system", "private",
			"volumes", "cores", "dev":
			return true
		}
	}
	return false
}
