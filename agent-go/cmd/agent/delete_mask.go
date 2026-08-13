package main
 
import (
	"context"
	"crypto/sha256"
	"encoding/base32"
	"fmt"
	"log"
	"os"
	"regexp"
	"sort"
	"strings"
 
	"dpdp-toolkit/agent-go/internal/client"
	"dpdp-toolkit/agent-go/internal/types"
)

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

var deletionTokenSalt = getEnv("DELETION_TOKEN", "abcde12345fghij67890")
 
type deleteRedactionResult struct {
	changed      bool
	blocks       int
	replacements int
	values       int
	entries      []types.DeleteReplacement
}
 
func applyDeletePlan(ctx context.Context, apiClient *client.Client, plan remediationPlan) {
	status := "completed"
	totalFilesChanged := 0
	totalBlocksChanged := 0
	totalReplacements := 0
	totalValuesMasked := 0
	deleteEntries := make([]types.DeleteReplacement, 0)
 
	for _, match := range plan.matches {
		result, err := redactDeleteFile(match.File, plan.targetValue)
		if err != nil {
			log.Printf("[DELETE] failed file=%s err=%v", match.File, err)
			status = "failed"
			continue
		}
		if result.changed {
			totalFilesChanged++
			totalBlocksChanged += result.blocks
			totalReplacements += result.replacements
			totalValuesMasked += result.values
			deleteEntries = append(deleteEntries, result.entries...)
		}
	}
 
	log.Printf(
		"[DELETE] task=%s target=%q files_changed=%d blocks_changed=%d values_masked=%d replacements=%d delete_entries=%d",
		plan.task.ID,
		plan.targetValue,
		totalFilesChanged,
		totalBlocksChanged,
		totalValuesMasked,
		totalReplacements,
		len(deleteEntries),
	)
 
	if status != "completed" {
		apiClient.SubmitResult(ctx, types.TaskResultPayload{
			TaskID:            plan.task.ID,
			DeviceID:          plan.task.DeviceID,
			Status:            status,
			ScannedFiles:      plan.scannedFiles,
			Matches:           plan.matches,
			DeleteReplacements: deleteEntries,
		})
	}
}
 
func redactDeleteFile(filePath, targetValue string) (deleteRedactionResult, error) {
	result, updated, err := buildDeleteRedaction(filePath, targetValue)
	if err != nil {
		return deleteRedactionResult{}, err
	}
	if !result.changed {
		return result, nil
	}
 
	if err := os.WriteFile(filePath, []byte(updated), 0644); err != nil {
		return deleteRedactionResult{}, err
	}
 
	return result, nil
}
 
func buildDeleteRedaction(filePath, targetValue string) (deleteRedactionResult, string, error) {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return deleteRedactionResult{}, "", err
	}
 
	original := string(content)
	blocks, separator := splitDeletionBlocks(original)
	changed := false
	totalBlocks := 0
	totalReplacements := 0
	totalValues := 0
	entries := make([]types.DeleteReplacement, 0)
 
	for i, block := range blocks {
		if !containsInsensitive(block, targetValue) {
			continue
		}
 
		signature := deletionSignature(block)
		replacements := buildDeleteReplacements(targetValue)
		if len(replacements) == 0 {
			continue
		}
 
		maskedBlock, blockReplacements := applyDeleteReplacements(block, replacements)
		if blockReplacements == 0 {
			continue
		}
 
		blocks[i] = maskedBlock
		changed = true
		totalBlocks++
		totalReplacements += blockReplacements
		totalValues += len(replacements)
 
		for originalValue, maskedValue := range replacements {
			entries = append(entries, types.DeleteReplacement{
				File:           filePath,
				OriginalValue:  originalValue,
				MaskedValue:    maskedValue,
				BlockSignature: signature,
			})
		}
 
		log.Printf(
			"[DELETE] file=%s signature=%s values=%d replacements=%d",
			filePath,
			signatureShort(signature),
			len(replacements),
			blockReplacements,
		)
	}
 
	if !changed {
		return deleteRedactionResult{changed: false}, original, nil
	}
 
	updated := strings.Join(blocks, separator)
	if strings.HasSuffix(original, "\n") && !strings.HasSuffix(updated, "\n") {
		updated += "\n"
	}
 
	if len(entries) > 1 {
		sort.SliceStable(entries, func(i, j int) bool {
			if entries[i].File == entries[j].File {
				if entries[i].BlockSignature == entries[j].BlockSignature {
					return entries[i].OriginalValue < entries[j].OriginalValue
				}
				return entries[i].BlockSignature < entries[j].BlockSignature
			}
			return entries[i].File < entries[j].File
		})
	}
 
	return deleteRedactionResult{
		changed:      true,
		blocks:       totalBlocks,
		replacements: totalReplacements,
		values:       totalValues,
		entries:      entries,
	}, updated, nil
}
 
func splitDeletionBlocks(content string) ([]string, string) {
	if strings.Contains(content, "\n\n") {
		parts := strings.Split(content, "\n\n")
		return parts, "\n\n"
	}
 
	lines := strings.Split(content, "\n")
	blocks := make([]string, 0, len(lines))
	for _, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}
		blocks = append(blocks, line)
	}
	if len(blocks) == 0 {
		return []string{content}, "\n"
	}
	return blocks, "\n"
}
 
func deletionSignature(block string) string {
	sum := sha256.Sum256([]byte(strings.ToLower(strings.TrimSpace(block))))
	return fmt.Sprintf("%x", sum[:])
}
 
func signatureShort(signature string) string {
	if len(signature) <= 12 {
		return signature
	}
	return signature[:12]
}

func buildDeleteReplacements(targetValue string) map[string]string {
	tokens := make(map[string]string)
	
	if targetValue != "" {
		tokens[targetValue] = stableDeletionToken(targetValue)
	}
 
	return tokens
}
 
func applyDeleteReplacements(content string, replacements map[string]string) (string, int) {
	if len(replacements) == 0 {
		return content, 0
	}
 
	type pair struct {
		old string
		new string
	}
 
	pairs := make([]pair, 0, len(replacements))
	for old, newValue := range replacements {
		pairs = append(pairs, pair{old: old, new: newValue})
	}
 
	sort.SliceStable(pairs, func(i, j int) bool {
		if len(pairs[i].old) == len(pairs[j].old) {
			return pairs[i].old < pairs[j].old
		}
		return len(pairs[i].old) > len(pairs[j].old)
	})
 
	updated := content
	total := 0
	for _, p := range pairs {
		var count int
		updated, count = replaceInsensitive(updated, p.old, p.new)
		total += count
	}
 
	return updated, total
}
 
func replaceInsensitive(content, oldValue, newValue string) (string, int) {
	if strings.TrimSpace(oldValue) == "" {
		return content, 0
	}
 
	re := regexp.MustCompile("(?i)" + regexp.QuoteMeta(oldValue))
	matches := re.FindAllStringIndex(content, -1)
	if len(matches) == 0 {
		return content, 0
	}
 
	return re.ReplaceAllString(content, newValue), len(matches)
}
 
func stableDeletionToken(original string) string {
	if strings.TrimSpace(original) == "" {
		return original
	}
 
	if len(original) <= 4 {
		sum := sha256.Sum256([]byte(deletionTokenSalt + "|" + original))
		return strings.ToLower(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(sum[:])[:8])
	}
 
	sum := sha256.Sum256([]byte(deletionTokenSalt + "|" + original))
	encoded := strings.ToLower(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(sum[:]))
	middleLen := len(original) - 4
	if middleLen > len(encoded) {
		repeated := encoded
		for len(repeated) < middleLen {
			repeated += encoded
		}
		encoded = repeated
	}
	return original[:2] + encoded[:middleLen] + original[len(original)-2:]
}
 
func containsInsensitive(haystack, needle string) bool {
	if needle == "" {
		return false
	}
	return strings.Contains(strings.ToLower(haystack), strings.ToLower(needle))
}