package scanner

import (
	"archive/zip"
	"bufio"
	"bytes"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	pdf "github.com/ledongthuc/pdf"

	"dpdp-toolkit/agent-go/internal/config"
	"dpdp-toolkit/agent-go/internal/pii"
	"dpdp-toolkit/agent-go/internal/types"
)

type Engine struct {
	cfg config.Config
}

func New(cfg config.Config) *Engine {
	return &Engine{cfg: cfg}
}

func (e *Engine) ScanTask(task types.Task) ([]types.Match, int) {
	roots := normalizedRoots(e.cfg.ScanPaths)
	if len(task.Paths) > 0 {
		roots = normalizedRoots(task.Paths)
	}

	query := strings.TrimSpace(strings.ToLower(task.Query))
	allMatches, scannedFiles := e.scanRoots(roots, query, task.Query)

	if scannedFiles == 0 && len(task.Paths) > 0 {
		fallbackRoots := normalizedRoots(e.cfg.ScanPaths)
		fallbackMatches, fallbackScanned := e.scanRoots(fallbackRoots, query, task.Query)
		allMatches = append(allMatches, fallbackMatches...)
		scannedFiles += fallbackScanned
	}

	return allMatches, scannedFiles
}

func (e *Engine) scanRoots(roots []string, query string, originalQuery string) ([]types.Match, int) {
	allMatches := make([]types.Match, 0)
	scannedFiles := 0

	for _, root := range roots {
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

			// Count file candidates even when extraction fails.
			scannedFiles++

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

			for _, p := range piiHits {
				allMatches = append(allMatches, types.Match{
					Type:  p.Type,
					Value: p.Value,
					File:  filePath,
				})
			}

			if queryHit && len(piiHits) == 0 {
				allMatches = append(allMatches, types.Match{
					Type:  "QUERY_HIT",
					Value: originalQuery,
					File:  filePath,
				})
			}

			return nil
		})

		if walkErr != nil {
			log.Printf("scan root skipped: root=%s error=%v", root, walkErr)
		}
	}

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
	ext := strings.ToLower(filepath.Ext(filePath))
	_, ok := e.cfg.IncludeExts[ext]
	return ok
}

func shouldSkipDir(name string) bool {
	n := strings.ToLower(name)
	switch n {
	case ".git", "node_modules", "appdata", "$recycle.bin", "windows", "program files", "program files (x86)":
		return true
	default:
		return false
	}
}

func readLimitedText(filePath string, maxBytes int64) (string, bool) {
	f, err := os.Open(filePath)
	if err != nil {
		return "", false
	}
	defer f.Close()

	reader := bufio.NewReader(io.LimitReader(f, maxBytes+1))
	b, err := io.ReadAll(reader)
	if err != nil {
		return "", false
	}
	if int64(len(b)) > maxBytes {
		return "", false
	}

	if !isLikelyText(b) {
		return "", false
	}

	return string(b), true
}

func extractText(filePath string, maxBytes int64) (string, bool) {
	ext := strings.ToLower(filepath.Ext(filePath))

	switch ext {
	case ".pdf":
		if text, ok := readPDFText(filePath, maxBytes); ok {
			return text, true
		}
	case ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp":
		if text, ok := readZipXMLText(filePath, maxBytes); ok {
			return text, true
		}
	}

	if text, ok := readLimitedText(filePath, maxBytes); ok {
		return text, true
	}

	if text, ok := readPrintableStrings(filePath, maxBytes); ok {
		return text, true
	}

	return "", false
}

func readPDFText(filePath string, maxBytes int64) (string, bool) {
	f, reader, err := pdf.Open(filePath)
	if err != nil {
		return "", false
	}
	defer f.Close()

	plain, err := reader.GetPlainText()
	if err != nil {
		return "", false
	}

	b, err := io.ReadAll(io.LimitReader(plain, maxBytes+1))
	if err != nil || int64(len(b)) > maxBytes {
		return "", false
	}

	text := strings.TrimSpace(string(b))
	if text == "" {
		return "", false
	}
	return text, true
}

func readZipXMLText(filePath string, maxBytes int64) (string, bool) {
	zr, err := zip.OpenReader(filePath)
	if err != nil {
		return "", false
	}
	defer zr.Close()

	var out strings.Builder
	tagRe := regexp.MustCompile(`<[^>]+>`)
	written := int64(0)

	for _, f := range zr.File {
		name := strings.ToLower(f.Name)
		if !strings.HasSuffix(name, ".xml") {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			continue
		}
		data, err := io.ReadAll(io.LimitReader(rc, maxBytes+1))
		rc.Close()
		if err != nil {
			continue
		}

		plain := tagRe.ReplaceAllString(string(data), " ")
		plain = strings.Join(strings.Fields(plain), " ")
		if plain == "" {
			continue
		}

		chunk := fmt.Sprintf("\n[%s]\n%s\n", f.Name, plain)
		if written+int64(len(chunk)) > maxBytes {
			break
		}
		out.WriteString(chunk)
		written += int64(len(chunk))
	}

	final := strings.TrimSpace(out.String())
	if final == "" {
		return "", false
	}
	return final, true
}

func readPrintableStrings(filePath string, maxBytes int64) (string, bool) {
	f, err := os.Open(filePath)
	if err != nil {
		return "", false
	}
	defer f.Close()

	b, err := io.ReadAll(io.LimitReader(f, maxBytes+1))
	if err != nil || int64(len(b)) > maxBytes {
		return "", false
	}

	var out strings.Builder
	seq := bytes.Buffer{}

	flush := func() {
		if seq.Len() >= 4 {
			if out.Len() > 0 {
				out.WriteByte('\n')
			}
			out.WriteString(seq.String())
		}
		seq.Reset()
	}

	for _, c := range b {
		if isPrintableASCII(c) {
			seq.WriteByte(c)
		} else {
			flush()
		}
	}
	flush()

	text := strings.TrimSpace(out.String())
	if text == "" {
		return "", false
	}
	return text, true
}

func isPrintableASCII(c byte) bool {
	return c == 9 || c == 10 || c == 13 || (c >= 32 && c <= 126)
}

func isLikelyText(b []byte) bool {
	if len(b) == 0 {
		return true
	}
	nonPrintable := 0
	for _, c := range b {
		if c == 0 {
			return false
		}
		if c < 9 || (c > 13 && c < 32) {
			nonPrintable++
		}
	}
	ratio := float64(nonPrintable) / float64(len(b))
	return ratio < 0.05
}
