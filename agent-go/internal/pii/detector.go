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
	"EMAIL":        regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`), // Single dot escape
	"PHONE_IN":     regexp.MustCompile(`\b[6-9]\d{9}\b`),                                 // Single backslash for \b and \d
	"PAN":          regexp.MustCompile(`\b[A-Z]{5}[0-9]{4}[A-Z]\b`),
	"AADHAAR":      regexp.MustCompile(`\b\d{4}[ -]?\d{4}[ -]?\d{4}\b`),
	"IP_ADDRESS":   regexp.MustCompile(`\b(?:\d{1,3}\.){3}\d{1,3}\b`),
	"IFSC":         regexp.MustCompile(`\b[A-Z]{4}0[A-Z0-9]{6}\b`),
	"BANK_ACCOUNT": regexp.MustCompile(`\b\d{9,18}\b`),
	"PASSPORT_IN":  regexp.MustCompile(`\b[A-Z][0-9]{7}\b`),
	"VOTER_ID":     regexp.MustCompile(`\b[A-Z]{3}[0-9]{7}\b`),
	"DRIVING_LICENSE_IN": regexp.MustCompile(`\b[A-Z]{2}[0-9]{2}[0-9]{4}[0-9]{7}\b`),
	"UPI_ID":             regexp.MustCompile(`\b[A-Z0-9._-]{2,256}@[A-Z]{2,64}\b`),
}

var creditCardPattern = regexp.MustCompile(`\b(?:\d{4}[- ]?){3}\d{4}\b`)

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

	for _, v := range detectCreditCards(content, maxPerType) {
		results = append(results, Match{
			Type:  "CREDIT_CARD",
			Value: maskValue(v),
		})
	}

	return results
}

func detectCreditCards(content string, maxPerType int) []string {
	found := creditCardPattern.FindAllString(content, maxPerType*3)
	if len(found) == 0 {
		return nil
	}

	out := make([]string, 0, maxPerType)
	seen := map[string]struct{}{}

	for _, card := range found {
		clean := strings.NewReplacer("-", "", " ", "").Replace(card)
		if len(clean) != 16 {
			continue
		}
		if _, ok := seen[clean]; ok {
			continue
		}
		if !isLuhnValid(clean) {
			continue
		}

		seen[clean] = struct{}{}
		out = append(out, card)
		if len(out) >= maxPerType {
			break
		}
	}

	return out
}

func isLuhnValid(number string) bool {
	sum := 0
	alt := false

	for i := len(number) - 1; i >= 0; i-- {
		c := number[i]
		if c < '0' || c > '9' {
			return false
		}

		d := int(c - '0')
		if alt {
			d *= 2
			if d > 9 {
				d -= 9
			}
		}
		sum += d
		alt = !alt
	}

	return sum%10 == 0
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
