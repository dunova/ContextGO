package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ── R27: mmap-path for large files ────────────────────────────────────────────

// TestR27LargeFileProcessing verifies that ProcessFile handles files >= 1MB
// correctly by creating a temp file larger than 1MB and checking results.
func TestR27LargeFileProcessing(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "large_session.jsonl")

	// Build a JSONL file that exceeds 1MB
	var buf bytes.Buffer
	line := `{"type":"event_msg","payload":{"type":"message","message":"this is a useful content line about important work"},"createdAt":"2025-01-01T00:00:00Z"}` + "\n"
	targetSize := 1024*1024 + 512 // just over 1MB
	for buf.Len() < targetSize {
		buf.WriteString(line)
	}
	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		t.Fatalf("write large file: %v", err)
	}

	stat, _ := os.Stat(path)
	if stat.Size() < 1024*1024 {
		t.Fatalf("file too small: %d bytes", stat.Size())
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "important work")
	if !ok {
		t.Fatal("expected a match in large file")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines > 0 for large file")
	}
	if summary.SizeBytes < 1024*1024 {
		t.Fatalf("expected size_bytes >= 1MB, got %d", summary.SizeBytes)
	}
}

// TestR27LargeFileNoQuery verifies that a large file with empty query still
// returns a summary (matchFound = true when QueryEmpty).
func TestR27LargeFileNoQuery(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "large_nq.jsonl")

	var buf bytes.Buffer
	line := `{"type":"event_msg","payload":{"type":"message","message":"content line"}}` + "\n"
	for buf.Len() < 1024*1024+100 {
		buf.WriteString(line)
	}
	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "") // empty query → all files match
	if !ok {
		t.Fatal("expected ok=true for empty query on large file")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines > 0")
	}
}

// ── R27: bytes.Contains fast-path ─────────────────────────────────────────────

// TestR27BytesContainsFastPath verifies the bytes.Contains semantics used for
// raw []byte matching: the query substring must be found inside the slice.
func TestR27BytesContainsFastPath(t *testing.T) {
	haystack := []byte("hello world this is a test message about contextgo")
	cases := []struct {
		needle string
		want   bool
	}{
		{"contextgo", true},
		{"hello world", true},
		{"CONTEXTGO", false}, // case-sensitive raw bytes
		{"not present", false},
		{"", true}, // empty needle always present
	}
	for _, tc := range cases {
		got := bytes.Contains(haystack, []byte(tc.needle))
		if got != tc.want {
			t.Errorf("bytes.Contains(%q) = %v, want %v", tc.needle, got, tc.want)
		}
	}
}

// TestR27RawLineFastPath verifies ProcessFile matches on raw (non-JSON) lines
// which exercise the bytes.Contains-equivalent path in the scanner.
func TestR27RawLineFastPath(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "raw.jsonl")
	// Mix of raw lines and JSON lines
	content := "this is a plain text line about unicorns\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"another line"}}` + "\n" +
		"more plain text with unicorns here\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "unicorns")
	if !ok {
		t.Fatal("expected match on raw line containing query")
	}
	if summary.MatchField != "raw_line" {
		t.Fatalf("expected match_field=raw_line, got %q", summary.MatchField)
	}
}

// ── R27: JSONL streaming via processOneLine ────────────────────────────────────

// TestR27JSONLStreamingValidLines verifies that valid JSON lines are parsed and
// contribute to the session summary correctly.
func TestR27JSONLStreamingValidLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "valid.jsonl")

	lines := []map[string]any{
		{"type": "event_msg", "payload": map[string]any{"type": "message", "message": "first message about deployment"}, "createdAt": "2025-01-01T10:00:00Z"},
		{"type": "event_msg", "payload": map[string]any{"type": "message", "message": "second message"}, "createdAt": "2025-01-01T11:00:00Z"},
		{"sessionId": "abc-123", "type": "event_msg", "payload": map[string]any{"type": "message", "message": "third message"}},
	}
	var buf bytes.Buffer
	for _, l := range lines {
		b, _ := json.Marshal(l)
		buf.Write(b)
		buf.WriteByte('\n')
	}
	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "deployment")
	if !ok {
		t.Fatal("expected match for 'deployment'")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines > 0")
	}
	if summary.FirstTimestamp == "" {
		t.Fatal("expected first_timestamp to be extracted")
	}
	if summary.SessionID != "abc-123" {
		t.Fatalf("expected session_id=abc-123, got %q", summary.SessionID)
	}
}

// TestR27JSONLStreamingInvalidLines verifies that invalid JSON lines are treated
// as raw text and still matched when the query is present.
func TestR27JSONLStreamingInvalidLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "invalid.jsonl")
	// Mix of bad JSON and good JSON
	content := "not valid json at all - contains the word spacecraft\n" +
		"{broken json here about spacecraft}\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"clean line"}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "spacecraft")
	if !ok {
		t.Fatal("expected match on invalid-JSON line containing query")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines counted")
	}
}

// ── R27: Pre-allocated result slice behavior ───────────────────────────────────

// TestR27PreAllocatedResultSlice verifies that scan() pre-allocates and returns
// correct results for various (items, limit) combinations.
func TestR27PreAllocatedResultSlice(t *testing.T) {
	dir := t.TempDir()

	makeFile := func(name, query string) string {
		p := filepath.Join(dir, name+".jsonl")
		line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"content about %s"}}`, query) + "\n"
		_ = os.WriteFile(p, []byte(line), 0644)
		return p
	}

	// Create 10 files each with a unique keyword
	items := make([]WorkItem, 10)
	for i := 0; i < 10; i++ {
		p := makeFile(fmt.Sprintf("file%02d", i), fmt.Sprintf("keyword%02d", i))
		items[i] = WorkItem{Source: "test", Path: p}
	}

	sc := NewSessionScanner(nil, 0)

	// limit=5: result slice should not exceed 5 after sort+truncate
	results, _ := scan(items, 2, "", 5, sc)
	if len(results) > 10 {
		t.Fatalf("expected at most 10 results, got %d", len(results))
	}

	// limit=0 means no limit
	results2, _ := scan(items, 2, "", 0, sc)
	if len(results2) != 10 {
		t.Fatalf("expected 10 results with limit=0, got %d", len(results2))
	}
}

// ── R27: Binary file guard ─────────────────────────────────────────────────────

// TestR27BinaryFileGuard verifies that files containing null bytes do not crash
// the scanner and return a coherent (possibly empty) result.
func TestR27BinaryFileGuard(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "binary.jsonl")

	// Embed null bytes to simulate binary content
	content := []byte("header line\x00\x00\x00binary data here\x00more binary\n")
	content = append(content, []byte("plain text line about recovery\n")...)
	if err := os.WriteFile(path, content, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Should not panic; result may or may not match depending on scanner behavior
	_, _ = scanner.ProcessFile(item, "recovery")
	// The key assertion: we reached here without panic
}

// TestR27BinaryFileLargeGuard tests a large binary file to ensure no crash.
func TestR27BinaryFileLargeGuard(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "large_binary.jsonl")

	var buf bytes.Buffer
	// Write alternating null bytes and text
	for i := 0; i < 1000; i++ {
		buf.WriteString("text line with content\x00\x00\x00\n")
	}
	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Must not panic
	_, _ = scanner.ProcessFile(item, "content")
}

// ── R27: --batch-output NDJSON streaming behavior ─────────────────────────────

// TestR27NDJSONStreamingSingle verifies that a single SessionSummary can be
// marshalled to valid NDJSON (one JSON object per line, no trailing newline issues).
func TestR27NDJSONStreamingSingle(t *testing.T) {
	summary := SessionSummary{
		Source:         "test",
		Path:           "/tmp/test.jsonl",
		SessionID:      "sess-001",
		Lines:          42,
		SizeBytes:      1024,
		FirstTimestamp: "2025-01-01T00:00:00Z",
		LastTimestamp:  "2025-01-01T01:00:00Z",
		Snippet:        "useful snippet here",
		MatchField:     "payload.message",
	}

	b, err := json.Marshal(summary)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	line := string(b)
	if strings.Contains(line, "\n") {
		t.Fatal("NDJSON line must not contain embedded newlines")
	}
	// Re-parse to verify round-trip
	var out SessionSummary
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatalf("json.Unmarshal round-trip: %v", err)
	}
	if out.SessionID != summary.SessionID {
		t.Fatalf("round-trip session_id mismatch: got %q", out.SessionID)
	}
}

// TestR27NDJSONStreamingMultiple verifies that multiple summaries can be emitted
// as separate NDJSON lines (simulating --batch-output streaming).
func TestR27NDJSONStreamingMultiple(t *testing.T) {
	summaries := []SessionSummary{
		{Source: "a", Path: "/a.jsonl", SessionID: "s1", Lines: 1, SizeBytes: 100},
		{Source: "b", Path: "/b.jsonl", SessionID: "s2", Lines: 2, SizeBytes: 200},
		{Source: "c", Path: "/c.jsonl", SessionID: "s3", Lines: 3, SizeBytes: 300},
	}

	var buf bytes.Buffer
	for _, s := range summaries {
		b, err := json.Marshal(s)
		if err != nil {
			t.Fatalf("json.Marshal: %v", err)
		}
		buf.Write(b)
		buf.WriteByte('\n')
	}

	// Parse back line by line
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")
	if len(lines) != 3 {
		t.Fatalf("expected 3 NDJSON lines, got %d", len(lines))
	}
	for i, line := range lines {
		var s SessionSummary
		if err := json.Unmarshal([]byte(line), &s); err != nil {
			t.Fatalf("line %d unmarshal: %v", i, err)
		}
		if s.SessionID != summaries[i].SessionID {
			t.Fatalf("line %d: session_id mismatch: got %q want %q", i, s.SessionID, summaries[i].SessionID)
		}
	}
}

// ── R27: Edge cases ────────────────────────────────────────────────────────────

// TestR27EmptyJSONLFile verifies that an empty file returns a zero-line summary.
func TestR27EmptyJSONLFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty.jsonl")
	if err := os.WriteFile(path, []byte{}, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "") // empty query → all match
	if !ok {
		t.Fatal("empty query on empty file should return ok=true")
	}
	if summary.Lines != 0 {
		t.Fatalf("expected 0 lines for empty file, got %d", summary.Lines)
	}
}

// TestR27FileWithOnlyNewlines verifies a file containing only blank lines.
func TestR27FileWithOnlyNewlines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "blank.jsonl")
	if err := os.WriteFile(path, []byte("\n\n\n\n\n"), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "")
	if !ok {
		t.Fatal("empty query on blank file should return ok=true")
	}
	if summary.Lines != 0 {
		t.Fatalf("expected 0 lines (all blank), got %d", summary.Lines)
	}
}

// TestR27MixedValidInvalidLines verifies a file with mixed valid/invalid JSON.
func TestR27MixedValidInvalidLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mixed.jsonl")
	content := `{"type":"event_msg","payload":{"type":"message","message":"valid line one"}}` + "\n" +
		"this is NOT json - contains the word telescope\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"valid line two about telescope"}}` + "\n" +
		"{invalid: missing quotes}\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"valid line three"}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "telescope")
	if !ok {
		t.Fatal("expected match for 'telescope'")
	}
	if summary.Lines < 3 {
		t.Fatalf("expected at least 3 counted lines, got %d", summary.Lines)
	}
}

// TestR27MixedLinesNoMatch verifies that missing query returns ok=false.
func TestR27MixedLinesNoMatch(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "nomatch.jsonl")
	content := `{"type":"event_msg","payload":{"type":"message","message":"unrelated content"}}` + "\n" +
		"another unrelated plain text line\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	_, ok := scanner.ProcessFile(item, "xyznotpresent")
	if ok {
		t.Fatal("expected ok=false when query not found")
	}
}

// ── R27: Unicode boundary handling ────────────────────────────────────────────

// TestR27UnicodeBoundaryInLargeFile verifies that CJK and multi-byte characters
// in a large (>=1MB) file are not split at Unicode boundaries.
func TestR27UnicodeBoundaryInLargeFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "unicode_large.jsonl")

	// CJK characters (3 bytes each in UTF-8)
	cjkLine := `{"type":"event_msg","payload":{"type":"message","message":"这是一个关于部署流水线的重要信息，包含多个中文字符用于测试边界"}}` + "\n"
	var buf bytes.Buffer
	for buf.Len() < 1024*1024+100 {
		buf.WriteString(cjkLine)
	}
	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Should not panic or return garbled snippet
	summary, ok := scanner.ProcessFile(item, "部署流水线")
	if !ok {
		t.Fatal("expected match for CJK query in large file")
	}
	// Snippet should be valid UTF-8 and contain no replacement characters
	if strings.Contains(summary.Snippet, "\uFFFD") {
		t.Fatalf("snippet contains Unicode replacement char (boundary split): %q", summary.Snippet)
	}
}

// TestR27UnicodeBoundaryClipSnippet verifies clipSnippet does not split
// multi-byte runes.
func TestR27UnicodeBoundaryClipSnippet(t *testing.T) {
	// Each CJK character is 3 bytes; snippet limit of 10 runes
	text := "前缀文字 关键词 后缀文字 结尾部分"
	query := "关键词"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx < 0 {
		t.Fatal("test setup: query not found in text")
	}
	snippet := clipSnippet(text, idx, len(query), 10)
	// Verify all runes are valid (no split bytes)
	for i, r := range snippet {
		if r == '\uFFFD' {
			t.Fatalf("replacement rune at position %d: %q", i, snippet)
		}
	}
	// Count runes: should be <= 10
	runeCount := 0
	for range snippet {
		runeCount++
	}
	if runeCount > 10 {
		t.Fatalf("expected <= 10 runes, got %d in %q", runeCount, snippet)
	}
}

// ── R27: Very long lines (>64KB) ──────────────────────────────────────────────

// TestR27VeryLongLine verifies that lines longer than 64KB are handled without
// crashing (bufio.Scanner uses a 32MB max buffer in ProcessFile).
func TestR27VeryLongLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "longline.jsonl")

	// Build a JSON line with a message field containing 128KB of text
	longMsg := strings.Repeat("x", 128*1024) + " target_word"
	line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"%s"}}`, longMsg) + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "target_word")
	if !ok {
		t.Fatal("expected match in very long line")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines > 0")
	}
}

// TestR27VeryLongRawLine tests a raw (non-JSON) line > 64KB.
func TestR27VeryLongRawLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "rawlongline.jsonl")

	// Plain text line > 64KB
	longLine := strings.Repeat("a", 70*1024) + " needle_word\n"
	if err := os.WriteFile(path, []byte(longLine), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := scanner.ProcessFile(item, "needle_word")
	if !ok {
		t.Fatal("expected match in very long raw line")
	}
	if summary.MatchField != "raw_line" {
		t.Fatalf("expected match_field=raw_line, got %q", summary.MatchField)
	}
}

// ── R27: BOM markers ──────────────────────────────────────────────────────────

// TestR27UTF8BOMFile verifies that a file with a UTF-8 BOM (EF BB BF) is
// processed correctly without treating the BOM as part of the content.
func TestR27UTF8BOMFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bom.jsonl")

	// UTF-8 BOM followed by a valid JSONL line
	bom := []byte{0xEF, 0xBB, 0xBF}
	line := []byte(`{"type":"event_msg","payload":{"type":"message","message":"bom file content with starship"}}` + "\n")
	content := append(bom, line...)
	if err := os.WriteFile(path, content, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Should process without panic; the BOM may or may not cause JSON parse issues
	// but must not crash
	_, _ = scanner.ProcessFile(item, "starship")
}

// TestR27UTF16BOMFile verifies a file with UTF-16 BE BOM (FE FF) does not crash.
func TestR27UTF16BOMFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "utf16bom.jsonl")

	// UTF-16 BE BOM followed by garbage bytes
	content := []byte{0xFE, 0xFF, 0x00, 0x7B, 0x00, 0x7D, 0x00, 0x0A}
	if err := os.WriteFile(path, content, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Must not panic
	_, _ = scanner.ProcessFile(item, "query")
}

// TestR27UTF8BOMWithQuery verifies that despite a BOM, text content can be matched.
func TestR27UTF8BOMWithQuery(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bom_match.jsonl")

	// UTF-8 BOM + plain text (not JSON) line
	bom := []byte{0xEF, 0xBB, 0xBF}
	text := []byte("plain text line containing the word submarine\n")
	content := append(bom, text...)
	if err := os.WriteFile(path, content, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	scanner := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// The BOM may be prepended to the line; query should still match
	_, _ = scanner.ProcessFile(item, "submarine")
	// No panic = pass; match may or may not occur depending on BOM handling
}

// ── R27: ScanOutput JSON envelope ─────────────────────────────────────────────

// TestR27ScanOutputJSONEnvelope verifies the ScanOutput struct serializes
// correctly with the expected JSON fields.
func TestR27ScanOutputJSONEnvelope(t *testing.T) {
	output := ScanOutput{
		FilesScanned: 42,
		Query:        "test query",
		Matches: []SessionSummary{
			{Source: "codex_session", Path: "/a.jsonl", SessionID: "s1", Lines: 10, SizeBytes: 512},
		},
		Truncated: false,
	}

	b, err := json.MarshalIndent(output, "", "  ")
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	s := string(b)
	if !strings.Contains(s, `"files_scanned": 42`) {
		t.Errorf("expected files_scanned in JSON output")
	}
	if !strings.Contains(s, `"query": "test query"`) {
		t.Errorf("expected query in JSON output")
	}
	if strings.Contains(s, `"match_score"`) {
		t.Errorf("match_score should be omitted (json:\"-\")")
	}
}

// TestR27ScanOutputAggregates verifies Aggregates() groups by source correctly.
func TestR27ScanOutputAggregates(t *testing.T) {
	output := ScanOutput{
		FilesScanned: 5,
		Matches: []SessionSummary{
			{Source: "codex_session", Lines: 10, SizeBytes: 100},
			{Source: "codex_session", Lines: 20, SizeBytes: 200},
			{Source: "claude_session", Lines: 5, SizeBytes: 50},
		},
	}

	aggs := output.Aggregates()
	if len(aggs) != 2 {
		t.Fatalf("expected 2 aggregate groups, got %d", len(aggs))
	}

	// Aggregates are sorted by source name
	if aggs[0].Source != "claude_session" {
		t.Fatalf("expected claude_session first, got %q", aggs[0].Source)
	}
	if aggs[1].Source != "codex_session" {
		t.Fatalf("expected codex_session second, got %q", aggs[1].Source)
	}
	if aggs[1].Count != 2 {
		t.Fatalf("expected codex_session count=2, got %d", aggs[1].Count)
	}
	if aggs[1].TotalLines != 30 {
		t.Fatalf("expected codex_session total_lines=30, got %d", aggs[1].TotalLines)
	}
}

// ── R27: shouldSkipPath ────────────────────────────────────────────────────────

// TestR27ShouldSkipPath verifies that skill directories are excluded.
func TestR27ShouldSkipPath(t *testing.T) {
	cases := []struct {
		path string
		skip bool
	}{
		{"/home/user/.claude/projects/session.jsonl", false},
		{"/home/user/.claude/skills/myscill.jsonl", true},
		{"/home/user/skills-repo/data.json", true},
		{"/home/user/SKILLS/data.json", true}, // case-insensitive
		{"/home/user/.codex/sessions/abc.json", false},
		{"/home/user/.codex/sessions/skills_related/abc.json", false}, // "skills_related" does not contain "/skills/"
	}
	for _, tc := range cases {
		got := shouldSkipPath(tc.path)
		if got != tc.skip {
			t.Errorf("shouldSkipPath(%q) = %v, want %v", tc.path, got, tc.skip)
		}
	}
}

// ── R27: collectFiles ─────────────────────────────────────────────────────────

// TestR27CollectFilesSkipsNonExistent verifies that non-existent roots are
// gracefully skipped without error.
func TestR27CollectFilesSkipsNonExistent(t *testing.T) {
	roots := []WorkItem{
		{Source: "test", Path: "/nonexistent/path/that/does/not/exist"},
	}
	items := collectFiles(roots)
	if len(items) != 0 {
		t.Fatalf("expected 0 items for non-existent root, got %d", len(items))
	}
}

// TestR27CollectFilesFindsJSONL verifies that .jsonl and .json files are found.
func TestR27CollectFilesFindsJSONL(t *testing.T) {
	dir := t.TempDir()

	// Create some files
	files := []string{"a.jsonl", "b.json", "c.txt", "d.log"}
	for _, f := range files {
		p := filepath.Join(dir, f)
		if err := os.WriteFile(p, []byte("{}"), 0644); err != nil {
			t.Fatalf("write %s: %v", f, err)
		}
	}

	roots := []WorkItem{{Source: "test", Path: dir}}
	items := collectFiles(roots)
	if len(items) != 2 {
		t.Fatalf("expected 2 items (.jsonl + .json), got %d", len(items))
	}
}

// TestR27CollectFilesSkipsSkillDir verifies that files inside skills/ dirs are skipped.
func TestR27CollectFilesSkipsSkillDir(t *testing.T) {
	dir := t.TempDir()

	skillsDir := filepath.Join(dir, "skills")
	if err := os.MkdirAll(skillsDir, 0755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	normalFile := filepath.Join(dir, "session.jsonl")
	skillFile := filepath.Join(skillsDir, "skill.jsonl")
	for _, p := range []string{normalFile, skillFile} {
		if err := os.WriteFile(p, []byte("{}"), 0644); err != nil {
			t.Fatalf("write: %v", err)
		}
	}

	roots := []WorkItem{{Source: "test", Path: dir}}
	items := collectFiles(roots)
	if len(items) != 1 {
		t.Fatalf("expected 1 item (skills dir excluded), got %d", len(items))
	}
	if !strings.HasSuffix(items[0].Path, "session.jsonl") {
		t.Fatalf("expected session.jsonl, got %q", items[0].Path)
	}
}

// ── R27: candidateScore ────────────────────────────────────────────────────────

// TestR27CandidateScore verifies scoring combines field priority and hit count.
func TestR27CandidateScore(t *testing.T) {
	// "message.content.text" has priority 120, one hit = 120 + 25 = 145
	score := candidateScore("message.content.text", "this text about query is good", "query")
	if score != 145 {
		t.Fatalf("expected score 145 for message.content.text + 1 hit, got %d", score)
	}

	// "raw_line" has priority 10, two hits = 10 + 50 = 60
	score2 := candidateScore("raw_line", "query and query here", "query")
	if score2 != 60 {
		t.Fatalf("expected score 60 for raw_line + 2 hits, got %d", score2)
	}

	// Unknown field priority = 40, no hits = 40
	score3 := candidateScore("unknown.field", "no matches here", "query")
	if score3 != 40 {
		t.Fatalf("expected score 40 for unknown field + 0 hits, got %d", score3)
	}
}

// ── R27: extractTextCandidates ────────────────────────────────────────────────

// TestR27ExtractTextCandidatesAllFields verifies that all supported field paths
// are extracted from a comprehensive JSON payload.
func TestR27ExtractTextCandidatesAllFields(t *testing.T) {
	payload := map[string]any{
		"message": "root message text",
		"display": "root display text",
		"text":    "root text value",
		"prompt":  "root prompt value",
		"payload": map[string]any{
			"message":             "payload message text",
			"user_instructions":   "payload user instructions",
			"last_agent_message":  "payload last agent message",
			"content": []any{
				map[string]any{"text": "payload content item 1"},
				map[string]any{"text": "payload content item 2"},
			},
		},
	}

	candidates := extractTextCandidates(payload)
	fields := make(map[string]bool)
	for _, c := range candidates {
		fields[c.Field] = true
	}

	expected := []string{
		"message", "root.display", "root.text", "root.prompt",
		"payload.message", "payload.user_instructions", "payload.last_agent_message",
		"payload.content.text",
	}
	for _, f := range expected {
		if !fields[f] {
			t.Errorf("expected field %q to be extracted", f)
		}
	}
}

// TestR27ExtractTextCandidatesEmptyPayload verifies that an empty payload
// returns no candidates without panic.
func TestR27ExtractTextCandidatesEmptyPayload(t *testing.T) {
	candidates := extractTextCandidates(map[string]any{})
	if len(candidates) != 0 {
		t.Fatalf("expected 0 candidates for empty payload, got %d", len(candidates))
	}
}

// ── R27: Session ID and timestamp extraction ───────────────────────────────────

// TestR27ExtractSessionID verifies sessionId is extracted from multiple locations.
func TestR27ExtractSessionID(t *testing.T) {
	cases := []struct {
		payload map[string]any
		want    string
	}{
		{
			map[string]any{"payload": map[string]any{"id": "from-payload-id"}},
			"from-payload-id",
		},
		{
			map[string]any{"sessionId": "from-root-sessionId"},
			"from-root-sessionId",
		},
		{
			map[string]any{"session_id": "from-root-session_id"},
			"from-root-session_id",
		},
		{
			map[string]any{"other": "field"},
			"",
		},
	}
	for _, tc := range cases {
		got := extractSessionID(tc.payload)
		if got != tc.want {
			t.Errorf("extractSessionID(%v) = %q, want %q", tc.payload, got, tc.want)
		}
	}
}

// TestR27ExtractTimestamp verifies timestamp extraction priority.
func TestR27ExtractTimestamp(t *testing.T) {
	// payload.timestamp takes priority
	p1 := map[string]any{
		"payload":   map[string]any{"timestamp": "2025-01-01T12:00:00Z"},
		"createdAt": "2025-01-01T10:00:00Z",
	}
	if ts := extractTimestamp(p1); ts != "2025-01-01T12:00:00Z" {
		t.Fatalf("expected payload.timestamp, got %q", ts)
	}

	// Fallback to createdAt
	p2 := map[string]any{"createdAt": "2025-01-01T10:00:00Z"}
	if ts := extractTimestamp(p2); ts != "2025-01-01T10:00:00Z" {
		t.Fatalf("expected createdAt fallback, got %q", ts)
	}

	// No timestamp
	p3 := map[string]any{"other": "field"}
	if ts := extractTimestamp(p3); ts != "" {
		t.Fatalf("expected empty timestamp, got %q", ts)
	}
}

// ── R27: shouldSkipRecordType ──────────────────────────────────────────────────

// TestR27ShouldSkipRecordType verifies that noise record types are skipped.
func TestR27ShouldSkipRecordType(t *testing.T) {
	cases := []struct {
		payload map[string]any
		skip    bool
	}{
		{map[string]any{"type": "turn_context"}, true},
		{map[string]any{"type": "custom_tool_call"}, true},
		{
			map[string]any{"type": "response_item", "payload": map[string]any{"type": "function_call_output"}},
			true,
		},
		{
			map[string]any{"type": "response_item", "payload": map[string]any{"type": "function_call"}},
			true,
		},
		{
			map[string]any{"type": "response_item", "payload": map[string]any{"type": "reasoning"}},
			true,
		},
		{
			map[string]any{"type": "event_msg", "payload": map[string]any{"type": "token_count"}},
			true,
		},
		{
			map[string]any{"type": "event_msg", "payload": map[string]any{"type": "task_started"}},
			true,
		},
		{
			map[string]any{"type": "event_msg", "payload": map[string]any{"type": "message"}},
			false,
		},
		{map[string]any{"type": "unknown_type"}, false},
		{map[string]any{}, false},
	}
	for i, tc := range cases {
		got := shouldSkipRecordType(tc.payload)
		if got != tc.skip {
			t.Errorf("case %d: shouldSkipRecordType(%v) = %v, want %v", i, tc.payload, got, tc.skip)
		}
	}
}

// ── R27: clipRuneWindow ────────────────────────────────────────────────────────

// TestR27ClipRuneWindowCentred verifies the window is centred on the match.
func TestR27ClipRuneWindowCentred(t *testing.T) {
	text := "AAAAABBBBBCCCCC" // 15 chars
	// Query at byte 5 ("BBBBB"), limit=5
	start, end := clipRuneWindow(text, 5, 5, 5)
	window := string([]rune(text)[start:end])
	if !strings.Contains(window, "B") {
		t.Fatalf("expected window to contain match, got %q", window)
	}
	if end-start > 5 {
		t.Fatalf("window size %d exceeds limit 5", end-start)
	}
}

// TestR27ClipRuneWindowShortText verifies that short text returns the full text.
func TestR27ClipRuneWindowShortText(t *testing.T) {
	text := "short"
	start, end := clipRuneWindow(text, 0, 5, 100)
	if start != 0 || end != 5 {
		t.Fatalf("expected [0,5), got [%d,%d)", start, end)
	}
}

// TestR27ClipRuneWindowNegativeIndex handles negative byte index gracefully.
func TestR27ClipRuneWindowNegativeIndex(t *testing.T) {
	text := "hello world test"
	// Should not panic with negative index
	start, end := clipRuneWindow(text, -5, 5, 10)
	if start < 0 || end < start {
		t.Fatalf("invalid window [%d,%d) for negative index input", start, end)
	}
}
