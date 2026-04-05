package pii

import (
	"regexp"
	"strings"
)

type Match struct {
	Type  string
	Value string
}

var patterns = map[string]*regexp.Regexp{
	"EMAIL":      regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}`),
	"PHONE_IN":   regexp.MustCompile(`\\b[6-9]\\d{9}\\b`),
	"PAN":        regexp.MustCompile(`\\b[A-Z]{5}[0-9]{4}[A-Z]\\b`),
	"AADHAAR":    regexp.MustCompile(`\\b\\d{4}[ -]?\\d{4}[ -]?\\d{4}\\b`),
	"IP_ADDRESS": regexp.MustCompile(`\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b`),
}

func Detect(content string, maxPerType int) []Match {
	if maxPerType <= 0 {
		maxPerType = 10
	}

	results := make([]Match, 0)
	upper := strings.ToUpper(content)

	for piiType, re := range patterns {
		found := re.FindAllString(upper, maxPerType)
		for _, v := range found {
			results = append(results, Match{
				Type:  piiType,
				Value: maskValue(v),
			})
		}
	}

	return results
}

func maskValue(v string) string {
	if len(v) <= 4 {
		return "****"
	}
	if strings.Contains(v, "@") {
		parts := strings.Split(v, "@")
		if len(parts) != 2 || len(parts[0]) < 2 {
			return "****"
		}
		return parts[0][:2] + "***@" + parts[1]
	}
	return v[:2] + strings.Repeat("*", len(v)-4) + v[len(v)-2:]
}
