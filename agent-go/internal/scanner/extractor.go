package scanner

import (
	"archive/zip"
	"bufio"
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	pdf "github.com/ledongthuc/pdf"
)

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