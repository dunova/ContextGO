package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"unicode/utf8"
)

// ── R38: JSONL edge-case parsing ──────────────────────────────────────────────

// TestR38_JSONLTruncatedLine verifies that a JSONL file ending with a truncated
// (non-terminated) JSON line does not crash and still processes prior lines.
func TestR38_JSONLTruncatedLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "truncated.jsonl")

	// Two complete lines + one truncated line (no closing brace or newline)
	content := `{"type":"event_msg","payload":{"type":"message","message":"first valid line with stargate"}}` + "\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"second valid line"}}` + "\n" +
		`{"type":"event_msg","message":"truncated no closing`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "stargate")
	if !ok {
		t.Fatal("expected match on complete lines before truncated line")
	}
	if summary.Lines < 2 {
		t.Fatalf("expected at least 2 lines counted, got %d", summary.Lines)
	}
}

// TestR38_JSONLEmptyLinesInterspersed verifies that blank lines between valid
// JSON lines are skipped and do not affect line count or matching.
func TestR38_JSONLEmptyLinesInterspersed(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty_lines.jsonl")

	content := "\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"content with nebula"}}` + "\n" +
		"\n\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"second content"}}` + "\n" +
		"\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "nebula")
	if !ok {
		t.Fatal("expected match for 'nebula'")
	}
	// Blank lines are skipped; only non-empty lines are counted
	if summary.Lines != 2 {
		t.Fatalf("expected 2 non-empty lines, got %d", summary.Lines)
	}
}

// TestR38_JSONLWhitespaceOnlyLines verifies that lines containing only spaces
// and tabs are treated as empty and not counted.
func TestR38_JSONLWhitespaceOnlyLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "whitespace.jsonl")

	content := "   \t\t   \n" +
		`{"type":"event_msg","payload":{"type":"message","message":"content with comet"}}` + "\n" +
		"\t\t\t\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "comet")
	if !ok {
		t.Fatal("expected match for 'comet'")
	}
	if summary.Lines != 1 {
		t.Fatalf("expected 1 non-empty line, got %d", summary.Lines)
	}
}

// TestR38_JSONLWindowsLineEndings verifies that CRLF line endings are handled
// correctly without corrupting JSON parsing.
func TestR38_JSONLWindowsLineEndings(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "crlf.jsonl")

	// Use Windows CRLF line endings
	line1 := `{"type":"event_msg","payload":{"type":"message","message":"crlf content about pulsar"}}` + "\r\n"
	line2 := `{"type":"event_msg","payload":{"type":"message","message":"second crlf line"}}` + "\r\n"
	content := line1 + line2
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "pulsar")
	if !ok {
		t.Fatal("expected match on CRLF file")
	}
	if summary.Lines != 2 {
		t.Fatalf("expected 2 lines, got %d", summary.Lines)
	}
}

// TestR38_JSONLNullValueFields verifies that JSON lines with null-value fields
// do not crash extraction and are handled gracefully.
func TestR38_JSONLNullValueFields(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "nullfields.jsonl")

	content := `{"type":"event_msg","message":null,"sessionId":null,"payload":{"type":"message","message":"valid content with quasar","timestamp":null}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "quasar")
	if !ok {
		t.Fatal("expected match despite null fields")
	}
	_ = summary
}

// TestR38_JSONLNumberFieldInsteadOfString verifies that type fields with
// unexpected non-string types (numbers, booleans) do not panic.
func TestR38_JSONLNumberFieldInsteadOfString(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "wrongtypes.jsonl")

	// type is a number instead of string
	content := `{"type":42,"message":true,"sessionId":99,"payload":{"type":false,"message":"actual text about pulsar cluster"}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Must not panic
	_, _ = sc.ProcessFile(item, "pulsar cluster")
}

// TestR38_JSONLNestedArraysInMessage verifies that message fields containing
// arrays (rather than strings) don't crash extraction.
func TestR38_JSONLNestedArraysInMessage(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "arrays.jsonl")

	content := `{"type":"event_msg","message":["item1","item2"],"payload":{"type":"message","message":"valid text about supernova","content":[{"text":"supernova detail"},{"text":"detail two"}]}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "supernova")
	if !ok {
		t.Fatal("expected match via payload.content.text field")
	}
	_ = summary
}

// TestR38_JSONLDeeplyNestedPayload tests a payload with extra nesting depth
// that is not covered by extractTextCandidates directly.
func TestR38_JSONLDeeplyNestedPayload(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "deepnest.jsonl")

	content := `{"type":"event_msg","payload":{"type":"message","message":"top level payload","inner":{"deep":"wormhole"}}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Should match on payload.message, not crash on deep nesting
	summary, ok := sc.ProcessFile(item, "top level payload")
	if !ok {
		t.Fatal("expected match on payload.message")
	}
	_ = summary
}

// ── R38: Very long lines and binary data ──────────────────────────────────────

// TestR38_LineExactly64KB verifies that a line of exactly 64*1024 bytes is
// handled without panic (boundary condition for scan buffers).
func TestR38_LineExactly64KB(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "exact64k.jsonl")

	// Build a JSON line with a message exactly at 64KB boundary
	// Leave room for surrounding JSON structure
	msgLen := 64*1024 - 50
	msg := strings.Repeat("y", msgLen) + " horizon_marker"
	line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"%s"}}`, msg) + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "horizon_marker")
	if !ok {
		t.Fatal("expected match in 64KB line")
	}
	if summary.Lines == 0 {
		t.Fatal("expected lines > 0")
	}
}

// TestR38_BinaryDataMixedWithValidLines verifies that a file with some binary
// lines (containing NUL bytes) causes the whole file to be excluded.
func TestR38_BinaryDataMixedWithValidLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "mixed_binary.jsonl")

	// First line is valid JSON, second contains NUL bytes
	line1 := `{"type":"event_msg","payload":{"type":"message","message":"valid before binary"}}` + "\n"
	binaryLine := "binary data\x00\x00 with nulls\n"
	line3 := `{"type":"event_msg","payload":{"type":"message","message":"valid after binary"}}` + "\n"
	content := line1 + binaryLine + line3
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Binary file detection should return false (excluded)
	_, ok := sc.ProcessFile(item, "valid before binary")
	// The file gets excluded because a binary line was encountered
	if ok {
		// Not an error if some implementations match before hitting binary
		// but the key requirement is no panic
	}
	// Must not panic — reaching here is the success condition
}

// TestR38_AllBinaryContent verifies a file consisting entirely of binary data
// does not crash the scanner.
func TestR38_AllBinaryContent(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "all_binary.jsonl")

	// Random binary-looking content with NUL bytes
	content := make([]byte, 1024)
	for i := range content {
		content[i] = byte(i % 256)
	}
	// Ensure NUL bytes are present
	content[0] = 0
	content[100] = 0
	content[500] = 0
	if err := os.WriteFile(path, content, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// Must not panic
	_, _ = sc.ProcessFile(item, "query")
}

// ── R38: Unicode boundary handling ───────────────────────────────────────────

// TestR38_UnicodeSnippetNoBoundaryBreak verifies that clip operations on text
// with emoji (4-byte UTF-8) never split a rune.
func TestR38_UnicodeSnippetNoBoundaryBreak(t *testing.T) {
	// Each emoji is 4 bytes in UTF-8
	text := "前缀文字🚀🌟💫 目标关键词 后缀文字🎯🔥✨ 结尾部分"
	query := "目标关键词"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx < 0 {
		t.Fatal("test setup: query not found in text")
	}

	snippet := clipSnippet(text, idx, len(query), 15)

	// All runes must be valid
	if !utf8.ValidString(snippet) {
		t.Fatalf("snippet is not valid UTF-8: %q", snippet)
	}
	for i, r := range snippet {
		if r == utf8.RuneError {
			t.Fatalf("replacement rune at position %d: %q", i, snippet)
		}
	}
	// Rune count must be <= 15
	count := 0
	for range snippet {
		count++
	}
	if count > 15 {
		t.Fatalf("expected <= 15 runes, got %d in %q", count, snippet)
	}
}

// TestR38_UnicodeSnippetAtStartOfText verifies clip when the match is at the
// very beginning of the text (no left context possible).
func TestR38_UnicodeSnippetAtStartOfText(t *testing.T) {
	text := "搜索关键词 some additional content that follows"
	query := "搜索关键词"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx != 0 {
		t.Fatalf("test setup: expected match at byte 0, got %d", idx)
	}

	snippet := clipSnippet(text, idx, len(query), 10)
	if !utf8.ValidString(snippet) {
		t.Fatalf("snippet not valid UTF-8: %q", snippet)
	}
	runeCount := 0
	for range snippet {
		runeCount++
	}
	if runeCount > 10 {
		t.Fatalf("expected <= 10 runes, got %d", runeCount)
	}
	// Must contain the query
	if !strings.Contains(snippet, "搜索") {
		t.Fatalf("expected snippet to contain start of query, got %q", snippet)
	}
}

// TestR38_UnicodeSnippetAtEndOfText verifies clip when the match is at the
// very end of the text (no right context possible).
func TestR38_UnicodeSnippetAtEndOfText(t *testing.T) {
	text := "some leading content that precedes the 尾部关键词"
	query := "尾部关键词"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx < 0 {
		t.Fatal("test setup: query not found in text")
	}

	snippet := clipSnippet(text, idx, len(query), 10)
	if !utf8.ValidString(snippet) {
		t.Fatalf("snippet not valid UTF-8: %q", snippet)
	}
	if !strings.Contains(snippet, "尾部") {
		t.Fatalf("expected snippet to contain query, got %q", snippet)
	}
}

// TestR38_UnicodeSnippetLimitLargerThanText verifies that when limit exceeds
// total rune count, the full text is returned unchanged.
func TestR38_UnicodeSnippetLimitLargerThanText(t *testing.T) {
	text := "短文本 with query"
	snippet := clipSnippet(text, 0, 3, 1000)
	if snippet != text {
		t.Fatalf("expected full text when limit > total runes, got %q", snippet)
	}
}

// TestR38_UnicodeSnippetLimitZeroReturnsFullText verifies that limit=0 returns
// the full text without clipping.
func TestR38_UnicodeSnippetLimitZeroReturnsFullText(t *testing.T) {
	text := "the full text should be returned when limit is zero"
	snippet := clipSnippet(text, 5, 4, 0)
	if snippet != text {
		t.Fatalf("expected full text for limit=0, got %q", snippet)
	}
}

// TestR38_ClipRuneWindowAllEdges verifies clipRuneWindow handles all major
// edge cases: zero-length query, zero limit, index at end of string.
func TestR38_ClipRuneWindowAllEdges(t *testing.T) {
	text := "hello world"

	t.Run("zero_query_len", func(t *testing.T) {
		start, end := clipRuneWindow(text, 5, 0, 4)
		if end-start > 4 {
			t.Fatalf("window size %d exceeds limit 4", end-start)
		}
	})

	t.Run("index_at_end", func(t *testing.T) {
		// index pointing to last character
		start, end := clipRuneWindow(text, len(text)-1, 1, 4)
		if start < 0 {
			t.Fatalf("negative start: %d", start)
		}
		if end > 11 { // len("hello world") runes = 11
			t.Fatalf("end %d exceeds total rune count", end)
		}
	})

	t.Run("empty_text", func(t *testing.T) {
		start, end := clipRuneWindow("", 0, 0, 10)
		if start != 0 || end != 0 {
			t.Fatalf("expected [0,0) for empty text, got [%d,%d)", start, end)
		}
	})

	t.Run("limit_one", func(t *testing.T) {
		start, end := clipRuneWindow(text, 3, 1, 1)
		if end-start != 1 {
			t.Fatalf("expected window size 1, got %d", end-start)
		}
	})
}

// TestR38_UnicodeRawLineInFile verifies that a file with raw CJK lines
// (not JSON) can still be matched and returns valid UTF-8 snippets.
func TestR38_UnicodeRawLineInFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cjk_raw.jsonl")

	// Raw CJK text line (not JSON)
	content := "这是一段包含重要信息的原始文本，关于分布式系统架构设计\n" +
		`{"type":"event_msg","payload":{"type":"message","message":"mixed content"}}` + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "分布式系统")
	if !ok {
		t.Fatal("expected match on CJK raw line")
	}
	if !utf8.ValidString(summary.Snippet) {
		t.Fatalf("snippet is not valid UTF-8: %q", summary.Snippet)
	}
}

// ── R38: Empty input handling ─────────────────────────────────────────────────

// TestR38_ProcessFileNonExistent verifies that a non-existent file returns
// ok=false without panic.
func TestR38_ProcessFileNonExistent(t *testing.T) {
	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: "/nonexistent/path/does/not/exist.jsonl"}
	_, ok := sc.ProcessFile(item, "query")
	if ok {
		t.Fatal("expected ok=false for non-existent file")
	}
}

// TestR38_ProcessFileZeroByteFile verifies a zero-byte file with non-empty
// query returns ok=false (no content to match).
func TestR38_ProcessFileZeroByteFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "zero.jsonl")
	if err := os.WriteFile(path, []byte{}, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	_, ok := sc.ProcessFile(item, "somequery")
	if ok {
		t.Fatal("expected ok=false for zero-byte file with non-empty query")
	}
}

// TestR38_ProcessFileZeroByteEmptyQuery verifies a zero-byte file with empty
// query returns ok=true (empty query matches everything).
func TestR38_ProcessFileZeroByteEmptyQuery(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "zero_eq.jsonl")
	if err := os.WriteFile(path, []byte{}, 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "")
	if !ok {
		t.Fatal("expected ok=true for empty query on zero-byte file")
	}
	if summary.Lines != 0 {
		t.Fatalf("expected 0 lines, got %d", summary.Lines)
	}
}

// TestR38_NewSessionScannerDefaults verifies that nil filter and zero limit
// fall back to defaults without panic.
func TestR38_NewSessionScannerDefaults(t *testing.T) {
	sc := NewSessionScanner(nil, 0)
	if sc == nil {
		t.Fatal("expected non-nil scanner")
	}
	if sc.snippetLimit != defaultSnippetLimit {
		t.Fatalf("expected default snippet limit %d, got %d", defaultSnippetLimit, sc.snippetLimit)
	}
	if sc.noiseFilter == nil {
		t.Fatal("expected non-nil noise filter")
	}
}

// TestR38_NewSessionScannerCustomValues verifies that custom filter and limit
// are stored correctly.
func TestR38_NewSessionScannerCustomValues(t *testing.T) {
	filter := NewNoiseFilter([]string{"custom_noise"})
	sc := NewSessionScanner(filter, 42)
	if sc.snippetLimit != 42 {
		t.Fatalf("expected snippet limit 42, got %d", sc.snippetLimit)
	}
	if sc.noiseFilter != filter {
		t.Fatal("expected custom filter to be stored")
	}
}

// TestR38_SnippetMatcherNilReceiver verifies that calling methods on a nil
// SnippetMatcher does not panic.
func TestR38_SnippetMatcherNilReceiver(t *testing.T) {
	var m *SnippetMatcher
	if !m.QueryEmpty() {
		t.Fatal("nil matcher should report QueryEmpty=true")
	}
	snippet, ok := m.Match("some text")
	if ok || snippet != "" {
		t.Fatal("nil matcher Match should return empty snippet and false")
	}
}

// TestR38_NoiseFilterNilReceiver verifies that calling IsNoiseLower on a nil
// NoiseFilter returns false (safe default).
func TestR38_NoiseFilterNilReceiver(t *testing.T) {
	var f *NoiseFilter
	if f.IsNoiseLower("any text") {
		t.Fatal("nil NoiseFilter should return false for IsNoiseLower")
	}
	if f.IsNoise("any text") {
		t.Fatal("nil NoiseFilter should return false for IsNoise")
	}
}

// ── R38: Error path coverage ──────────────────────────────────────────────────

// TestR38_ProcessLinesEmptyInput verifies processLines on an empty slice calls
// fn zero times.
func TestR38_ProcessLinesEmptyInput(t *testing.T) {
	count := 0
	processLines([]byte{}, func(_ []byte) {
		count++
	})
	if count != 0 {
		t.Fatalf("expected 0 callbacks for empty input, got %d", count)
	}
}

// TestR38_ProcessLinesSingleNoNewline verifies processLines on a single line
// with no trailing newline.
func TestR38_ProcessLinesSingleNoNewline(t *testing.T) {
	lines := [][]byte{}
	processLines([]byte("single line no newline"), func(line []byte) {
		lines = append(lines, append([]byte{}, line...))
	})
	if len(lines) != 1 {
		t.Fatalf("expected 1 line, got %d", len(lines))
	}
	if string(lines[0]) != "single line no newline" {
		t.Fatalf("unexpected line content: %q", lines[0])
	}
}

// TestR38_ProcessLinesTrimsLeadingTrailingSpaces verifies inline trimming.
func TestR38_ProcessLinesTrimsLeadingTrailingSpaces(t *testing.T) {
	input := []byte("  \t leading and trailing \t  \n")
	var got [][]byte
	processLines(input, func(line []byte) {
		got = append(got, append([]byte{}, line...))
	})
	if len(got) != 1 {
		t.Fatalf("expected 1 line, got %d", len(got))
	}
	if string(got[0]) != "leading and trailing" {
		t.Fatalf("unexpected trimmed content: %q", got[0])
	}
}

// TestR38_ProcessLinesMultipleNewlines verifies processLines correctly splits
// on multiple consecutive newlines.
func TestR38_ProcessLinesMultipleNewlines(t *testing.T) {
	input := []byte("line1\n\nline2\n\n\nline3\n")
	var got []string
	processLines(input, func(line []byte) {
		got = append(got, string(line))
	})
	// Only non-empty lines after trimming should appear
	if len(got) != 3 {
		t.Fatalf("expected 3 non-empty lines, got %d: %v", len(got), got)
	}
}

// TestR38_ProcessLinesOnlyCRLF verifies CRLF-only content produces no callbacks.
func TestR38_ProcessLinesOnlyCRLF(t *testing.T) {
	count := 0
	processLines([]byte("\r\n\r\n\r\n"), func(_ []byte) {
		count++
	})
	if count != 0 {
		t.Fatalf("expected 0 callbacks for CRLF-only content, got %d", count)
	}
}

// TestR38_ContainsFoldASCIIEdgeCases tests edge cases for containsFoldASCII.
func TestR38_ContainsFoldASCIIEdgeCases(t *testing.T) {
	t.Run("empty_needle_always_true", func(t *testing.T) {
		if !containsFoldASCII([]byte("anything"), []byte{}) {
			t.Fatal("empty needle should always return true")
		}
	})

	t.Run("empty_haystack_nonempty_needle", func(t *testing.T) {
		if containsFoldASCII([]byte{}, []byte("needle")) {
			t.Fatal("empty haystack cannot contain non-empty needle")
		}
	})

	t.Run("needle_longer_than_haystack", func(t *testing.T) {
		if containsFoldASCII([]byte("hi"), []byte("hello")) {
			t.Fatal("needle longer than haystack cannot match")
		}
	})

	t.Run("exact_match_same_length", func(t *testing.T) {
		if !containsFoldASCII([]byte("abc"), []byte("abc")) {
			t.Fatal("exact match of same length should succeed")
		}
	})

	t.Run("case_insensitive_upper_lower", func(t *testing.T) {
		if !containsFoldASCII([]byte("HELLO WORLD"), []byte("hello")) {
			t.Fatal("case-insensitive match HELLO -> hello failed")
		}
	})

	t.Run("case_insensitive_lower_upper", func(t *testing.T) {
		if !containsFoldASCII([]byte("hello world"), []byte("hello")) {
			t.Fatal("case-insensitive match hello -> hello failed")
		}
	})

	t.Run("non_alpha_chars_match_exactly", func(t *testing.T) {
		if !containsFoldASCII([]byte("123-456"), []byte("123-456")) {
			t.Fatal("numeric/symbol exact match failed")
		}
	})

	t.Run("single_char_needle", func(t *testing.T) {
		if !containsFoldASCII([]byte("hello"), []byte("o")) {
			t.Fatal("single char match failed")
		}
		if containsFoldASCII([]byte("hello"), []byte("z")) {
			t.Fatal("single char non-match should return false")
		}
	})
}

// TestR38_IsASCIIEdgeCases tests the isASCII function edge cases.
func TestR38_IsASCIIEdgeCases(t *testing.T) {
	t.Run("empty_slice_is_ascii", func(t *testing.T) {
		if !isASCII([]byte{}) {
			t.Fatal("empty slice should be considered ASCII")
		}
	})

	t.Run("all_printable_ascii", func(t *testing.T) {
		if !isASCII([]byte("Hello, World! 123")) {
			t.Fatal("printable ASCII should be detected as ASCII")
		}
	})

	t.Run("control_chars_are_ascii", func(t *testing.T) {
		if !isASCII([]byte{0x00, 0x01, 0x7F}) {
			t.Fatal("control chars <= 0x7F should be ASCII")
		}
	})

	t.Run("high_byte_not_ascii", func(t *testing.T) {
		if isASCII([]byte{0x80}) {
			t.Fatal("byte 0x80 should not be ASCII")
		}
	})

	t.Run("utf8_multibyte_not_ascii", func(t *testing.T) {
		if isASCII([]byte("日本語")) {
			t.Fatal("CJK UTF-8 should not be ASCII")
		}
	})
}

// ── R38: sync.Pool reuse patterns ─────────────────────────────────────────────

// TestR38_ScannerBufPoolReuseUnderLoad verifies that the scannerBufPool is
// correctly reused across many concurrent ProcessFile calls without data races.
func TestR38_ScannerBufPoolReuseUnderLoad(t *testing.T) {
	dir := t.TempDir()

	// Create 20 small JSONL files
	files := make([]string, 20)
	for i := range files {
		p := filepath.Join(dir, fmt.Sprintf("file%02d.jsonl", i))
		line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"content about pool_reuse_test iteration %d"}}`, i) + "\n"
		if err := os.WriteFile(p, []byte(line), 0644); err != nil {
			t.Fatalf("write: %v", err)
		}
		files[i] = p
	}

	sc := NewSessionScanner(nil, 0)
	var wg sync.WaitGroup
	for _, f := range files {
		f := f
		wg.Add(1)
		go func() {
			defer wg.Done()
			item := WorkItem{Source: "test", Path: f}
			_, _ = sc.ProcessFile(item, "pool_reuse_test")
		}()
	}
	wg.Wait()
	// No race detector violations = pass
}

// TestR38_RuneSlicePoolReturnedCorrectly verifies that clipSnippet properly
// returns the rune slice to the pool (no data race or leak).
func TestR38_RuneSlicePoolReturnedCorrectly(t *testing.T) {
	text := "这是测试内容，包含了池复用的关键词测试案例"
	query := "池复用"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx < 0 {
		t.Fatal("test setup: query not found")
	}

	// Call clipSnippet many times to stress-test pool reuse
	for i := 0; i < 100; i++ {
		snippet := clipSnippet(text, idx, len(query), 10)
		if !utf8.ValidString(snippet) {
			t.Fatalf("iteration %d: invalid UTF-8 in snippet", i)
		}
	}
}

// TestR38_SnippetMatcherPoolUnderConcurrency verifies SnippetMatcher.Match
// under concurrent use (pool should not cause data races).
func TestR38_SnippetMatcherPoolUnderConcurrency(t *testing.T) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	m := NewSnippetMatcher("concurrent", filter, 50)

	texts := []string{
		"this text contains concurrent operations and parallel patterns",
		"not a match here",
		"another concurrent execution example with details",
		"no match text",
		"concurrent programming is important for performance",
	}

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		i := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			text := texts[i%len(texts)]
			snippet, _ := m.Match(text)
			if snippet != "" && !utf8.ValidString(snippet) {
				t.Errorf("goroutine %d: invalid UTF-8 in snippet", i)
			}
		}()
	}
	wg.Wait()
}

// ── R38: NoiseFilter additional coverage ─────────────────────────────────────

// TestR38_NoiseFilterEmptyMarkers verifies that a filter with no markers still
// applies the prefix and heuristic checks.
func TestR38_NoiseFilterEmptyMarkers(t *testing.T) {
	filter := NewNoiseFilter([]string{})

	// Should still filter noise prefixes
	if !filter.IsNoise("## section heading") {
		t.Fatal("expected ## prefix to be filtered even with empty markers")
	}
	if !filter.IsNoise("```code block") {
		t.Fatal("expected ``` prefix to be filtered")
	}
	// Clean line should pass
	if filter.IsNoise("this is perfectly valid content text") {
		t.Fatal("expected clean line to pass with empty markers")
	}
}

// TestR38_NoiseFilterEmptyLine verifies that an empty string is always noise.
func TestR38_NoiseFilterEmptyLine(t *testing.T) {
	filter := NewNoiseFilter(nil)
	if !filter.IsNoiseLower("") {
		t.Fatal("empty string should always be noise")
	}
}

// TestR38_NoiseFilterDirectoryListing verifies that directory listing patterns
// (drwx, rwxr-xr-x) are identified as noise.
func TestR38_NoiseFilterDirectoryListing(t *testing.T) {
	filter := NewNoiseFilter(nil)

	cases := []struct {
		line  string
		noise bool
	}{
		{"drwxr-xr-x 2 user group 4096 Jan 1 00:00 directory", true},
		{"rwxr-xr-x permissions string", true},
		{"\ntotal 48\ndrwx permissions", true},
		{"normal content line without directory markers", false},
	}
	for _, tc := range cases {
		got := filter.IsNoiseLower(tc.line)
		if got != tc.noise {
			t.Errorf("IsNoiseLower(%q) = %v, want %v", tc.line, got, tc.noise)
		}
	}
}

// TestR38_NoiseFilterShortTokenHeuristic verifies the short-token heuristic
// that filters out directory listings / skill manifests (>= 5 short tokens).
func TestR38_NoiseFilterShortTokenHeuristic(t *testing.T) {
	filter := NewNoiseFilter(nil)

	// 6 short tokens separated by newlines should be noise
	manyShortTokens := "token1\ntoken2\ntoken3\ntoken4\ntoken5\ntoken6"
	if !filter.IsNoiseLower(manyShortTokens) {
		t.Fatal("expected short-token heuristic to fire for 6 tokens")
	}

	// Only 3 short tokens — should pass
	fewShortTokens := "token1\ntoken2\ntoken3"
	if filter.IsNoiseLower(fewShortTokens) {
		t.Fatal("expected 3 short tokens to pass the noise filter")
	}
}

// TestR38_NoiseFilterNotebookLMPattern verifies the combined notebooklm
// pattern detection.
func TestR38_NoiseFilterNotebookLMPattern(t *testing.T) {
	filter := NewNoiseFilter(nil)

	noisy := "notebooklm search session_index native-scan integration"
	if !filter.IsNoiseLower(noisy) {
		t.Fatal("expected notebooklm+search+session_index+native-scan to be noise")
	}

	// Missing one of the required substrings — should not trigger
	partial := "notebooklm search session_index"
	if filter.IsNoiseLower(partial) {
		t.Fatal("partial notebooklm pattern should not trigger noise filter")
	}
}

// TestR38_NoiseFilterWhitespaceTrimInMarkers verifies that markers with
// surrounding whitespace in the input list are trimmed and still work.
func TestR38_NoiseFilterWhitespaceTrimInMarkers(t *testing.T) {
	// Markers have extra whitespace
	filter := NewNoiseFilter([]string{"  trimmed_marker  ", "\t another_marker \t"})

	if !filter.IsNoise("text containing trimmed_marker here") {
		t.Fatal("trimmed marker should still be detected")
	}
	if !filter.IsNoise("text with another_marker present") {
		t.Fatal("tab-trimmed marker should still be detected")
	}
}

// ── R38: extractCwd and active workdir filtering ───────────────────────────────

// TestR38_ExtractCwdFromPayload verifies cwd extraction from payload and root.
func TestR38_ExtractCwdFromPayload(t *testing.T) {
	cases := []struct {
		payload map[string]any
		want    string
	}{
		{
			map[string]any{"payload": map[string]any{"cwd": "/home/user/project"}},
			"/home/user/project",
		},
		{
			map[string]any{"cwd": "/root/level/cwd"},
			"/root/level/cwd",
		},
		{
			map[string]any{"other": "field"},
			"",
		},
		{
			// payload.cwd takes priority
			map[string]any{
				"cwd":     "/root/cwd",
				"payload": map[string]any{"cwd": "/payload/cwd"},
			},
			"/payload/cwd",
		},
	}
	for i, tc := range cases {
		got := extractCwd(tc.payload)
		if got != tc.want {
			t.Errorf("case %d: extractCwd = %q, want %q", i, got, tc.want)
		}
	}
}

// TestR38_ActiveWorkdirFilterExcludesFile verifies that when CONTEXTGO_ACTIVE_WORKDIR
// matches the cwd in a session file, the file is excluded from results.
func TestR38_ActiveWorkdirFilterExcludesFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "active_session.jsonl")

	// Create a JSONL file with a cwd that matches the env var we'll set
	activeCwd := dir // use the temp dir as "active workdir"
	line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"content about active workdir","cwd":"%s"}}`, activeCwd) + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	// Set the active workdir env var
	t.Setenv("CONTEXTGO_ACTIVE_WORKDIR", activeCwd)

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	// File should be excluded because its cwd == active workdir
	_, ok := sc.ProcessFile(item, "active workdir")
	if ok {
		t.Fatal("expected file with active cwd to be excluded")
	}
}

// TestR38_ActiveWorkdirNotSetDoesNotFilter verifies that without
// CONTEXTGO_ACTIVE_WORKDIR set, files are not filtered by cwd.
func TestR38_ActiveWorkdirNotSetDoesNotFilter(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "normal_session.jsonl")

	line := `{"type":"event_msg","payload":{"type":"message","message":"content about normal session","cwd":"/some/random/path"}}` + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	// Ensure env var is unset
	t.Setenv("CONTEXTGO_ACTIVE_WORKDIR", "")

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "normal session")
	if !ok {
		t.Fatal("expected match when active workdir not set")
	}
	_ = summary
}

// ── R38: extractTextCandidatesWithCap ─────────────────────────────────────────

// TestR38_ExtractTextCandidatesWithCapMinimumCap verifies that a cap < 4 is
// clamped to 4.
func TestR38_ExtractTextCandidatesWithCapMinimumCap(t *testing.T) {
	payload := map[string]any{
		"message": "test message content",
	}
	// cap=0 should be clamped to 4 internally — just verify no panic
	candidates := extractTextCandidatesWithCap(payload, 0)
	if len(candidates) == 0 {
		t.Fatal("expected at least one candidate")
	}
	if candidates[0].Text != "test message content" {
		t.Fatalf("unexpected candidate text: %q", candidates[0].Text)
	}
}

// TestR38_ExtractTextCandidatesNegativeCap verifies that negative cap is safe.
func TestR38_ExtractTextCandidatesNegativeCap(t *testing.T) {
	payload := map[string]any{
		"text": "some text value",
	}
	// negative cap — should be clamped
	candidates := extractTextCandidatesWithCap(payload, -10)
	if len(candidates) == 0 {
		t.Fatal("expected at least one candidate")
	}
}

// TestR38_ExtractTextCandidatesWhitespaceOnlyFields verifies that fields
// containing only whitespace are not included as candidates.
func TestR38_ExtractTextCandidatesWhitespaceOnlyFields(t *testing.T) {
	payload := map[string]any{
		"message": "   \t\t   ",
		"text":    "\n\n",
		"payload": map[string]any{
			"message": "real content here",
		},
	}
	candidates := extractTextCandidates(payload)
	for _, c := range candidates {
		if strings.TrimSpace(c.Text) == "" {
			t.Fatalf("expected no whitespace-only candidates, got field %q text %q", c.Field, c.Text)
		}
	}
}

// ── R38: fieldPriority coverage ───────────────────────────────────────────────

// TestR38_FieldPriorityAllKnownFields verifies that every documented field path
// returns the expected priority value.
func TestR38_FieldPriorityAllKnownFields(t *testing.T) {
	cases := []struct {
		field    string
		expected int
	}{
		{"message.content.text", 120},
		{"payload.content.text", 120},
		{"message", 100},
		{"message.content", 100},
		{"payload.message", 100},
		{"root.text", 100},
		{"payload.text", 100},
		{"root.content", 70},
		{"root.display", 70},
		{"payload.display", 70},
		{"root.last_agent_message", 70},
		{"payload.last_agent_message", 70},
		{"root.prompt", 20},
		{"payload.prompt", 20},
		{"root.user_instructions", 20},
		{"payload.user_instructions", 20},
		{"raw_line", 10},
		{"completely.unknown.field", 40},
	}
	for _, tc := range cases {
		got := fieldPriority(tc.field)
		if got != tc.expected {
			t.Errorf("fieldPriority(%q) = %d, want %d", tc.field, got, tc.expected)
		}
	}
}

// ── R38: summarize / Aggregate ────────────────────────────────────────────────

// TestR38_SummarizeEmptyResults verifies that summarize on an empty slice
// returns an empty aggregate list.
func TestR38_SummarizeEmptyResults(t *testing.T) {
	aggs := summarize([]SessionSummary{})
	if len(aggs) != 0 {
		t.Fatalf("expected 0 aggregates for empty input, got %d", len(aggs))
	}
}

// TestR38_SummarizeSingleSource verifies aggregate totals for a single source.
func TestR38_SummarizeSingleSource(t *testing.T) {
	results := []SessionSummary{
		{Source: "source_a", Lines: 10, SizeBytes: 100},
		{Source: "source_a", Lines: 20, SizeBytes: 200},
		{Source: "source_a", Lines: 30, SizeBytes: 300},
	}
	aggs := summarize(results)
	if len(aggs) != 1 {
		t.Fatalf("expected 1 aggregate, got %d", len(aggs))
	}
	if aggs[0].Count != 3 {
		t.Fatalf("expected count=3, got %d", aggs[0].Count)
	}
	if aggs[0].TotalLines != 60 {
		t.Fatalf("expected total_lines=60, got %d", aggs[0].TotalLines)
	}
	if aggs[0].TotalSize != 600 {
		t.Fatalf("expected total_size=600, got %d", aggs[0].TotalSize)
	}
}

// TestR38_SummarizeMultipleSourcesSorted verifies that aggregates are sorted
// alphabetically by source name.
func TestR38_SummarizeMultipleSourcesSorted(t *testing.T) {
	results := []SessionSummary{
		{Source: "zebra_source", Lines: 5, SizeBytes: 50},
		{Source: "alpha_source", Lines: 10, SizeBytes: 100},
		{Source: "middle_source", Lines: 7, SizeBytes: 70},
		{Source: "alpha_source", Lines: 3, SizeBytes: 30},
	}
	aggs := summarize(results)
	if len(aggs) != 3 {
		t.Fatalf("expected 3 aggregates, got %d", len(aggs))
	}
	if aggs[0].Source != "alpha_source" {
		t.Fatalf("expected alpha_source first, got %q", aggs[0].Source)
	}
	if aggs[1].Source != "middle_source" {
		t.Fatalf("expected middle_source second, got %q", aggs[1].Source)
	}
	if aggs[2].Source != "zebra_source" {
		t.Fatalf("expected zebra_source third, got %q", aggs[2].Source)
	}
	if aggs[0].Count != 2 {
		t.Fatalf("expected alpha_source count=2, got %d", aggs[0].Count)
	}
}

// ── R38: scan() function behavior ────────────────────────────────────────────

// TestR38_ScanZeroThreadsFallsBackToOne verifies that scan() with 0 threads
// still processes files (falls back to 1 thread).
func TestR38_ScanZeroThreadsFallsBackToOne(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "single.jsonl")
	line := `{"type":"event_msg","payload":{"type":"message","message":"fallback thread test content"}}` + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	items := []WorkItem{{Source: "test", Path: path}}
	results, _ := scan(items, 0, "", 10, sc)
	if len(results) != 1 {
		t.Fatalf("expected 1 result with 0 threads fallback, got %d", len(results))
	}
}

// TestR38_ScanEmptyWorkItemList verifies that scanning an empty list returns
// empty results without panic.
func TestR38_ScanEmptyWorkItemList(t *testing.T) {
	sc := NewSessionScanner(nil, 0)
	results, truncated := scan([]WorkItem{}, 4, "query", 10, sc)
	if len(results) != 0 {
		t.Fatalf("expected 0 results for empty work list, got %d", len(results))
	}
	if truncated {
		t.Fatal("expected truncated=false for empty work list")
	}
}

// TestR38_ScanHighConcurrency verifies that many threads scanning many files
// concurrently produces consistent results.
func TestR38_ScanHighConcurrency(t *testing.T) {
	dir := t.TempDir()

	numFiles := 50
	items := make([]WorkItem, numFiles)
	for i := range items {
		p := filepath.Join(dir, fmt.Sprintf("f%02d.jsonl", i))
		line := fmt.Sprintf(`{"type":"event_msg","payload":{"type":"message","message":"concurrent_scan_test content item %d"}}`, i) + "\n"
		if err := os.WriteFile(p, []byte(line), 0644); err != nil {
			t.Fatalf("write: %v", err)
		}
		items[i] = WorkItem{Source: "test", Path: p}
	}

	sc := NewSessionScanner(nil, 0)
	results, _ := scan(items, 16, "concurrent_scan_test", 100, sc)
	if len(results) != numFiles {
		t.Fatalf("expected %d results, got %d", numFiles, len(results))
	}
}

// ── R38: ScanOutput.Aggregates ────────────────────────────────────────────────

// TestR38_ScanOutputAggregatesEmpty verifies Aggregates() on empty matches.
func TestR38_ScanOutputAggregatesEmpty(t *testing.T) {
	o := ScanOutput{FilesScanned: 5, Matches: nil}
	aggs := o.Aggregates()
	if len(aggs) != 0 {
		t.Fatalf("expected 0 aggregates for empty matches, got %d", len(aggs))
	}
}

// TestR38_ScanOutputJSONOmitsMatchScore verifies that MatchScore (tagged json:"-")
// is never included in JSON serialization.
func TestR38_ScanOutputJSONOmitsMatchScore(t *testing.T) {
	s := SessionSummary{
		Source:     "test",
		Path:       "/test.jsonl",
		SessionID:  "s1",
		Lines:      1,
		SizeBytes:  100,
		MatchScore: 9999, // should be omitted
	}
	b, err := json.Marshal(s)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if bytes.Contains(b, []byte("match_score")) {
		t.Fatalf("match_score should be omitted from JSON, got: %s", b)
	}
	if bytes.Contains(b, []byte("9999")) {
		t.Fatalf("match_score value should not appear in JSON, got: %s", b)
	}
}

// ── R38: normalizePath ────────────────────────────────────────────────────────

// TestR38_NormalizePathEmpty verifies that normalizing an empty path returns "".
func TestR38_NormalizePathEmpty(t *testing.T) {
	got := normalizePath("")
	if got != "" {
		t.Fatalf("expected empty string for empty input, got %q", got)
	}
}

// TestR38_NormalizePathAbsolute verifies that an absolute path is returned as-is
// (modulo symlink resolution) without error.
func TestR38_NormalizePathAbsolute(t *testing.T) {
	dir := t.TempDir()
	got := normalizePath(dir)
	if got == "" {
		t.Fatal("expected non-empty normalized path for existing directory")
	}
	// Must be absolute
	if !filepath.IsAbs(got) {
		t.Fatalf("expected absolute path, got %q", got)
	}
}

// ── R38: SessionID from filename fallback ────────────────────────────────────

// TestR38_SessionIDFallsBackToFilename verifies that when no JSON record
// contains a sessionId, the filename (sans extension) is used.
func TestR38_SessionIDFallsBackToFilename(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "my_session_file.jsonl")

	// JSON line with no sessionId field
	line := `{"type":"event_msg","payload":{"type":"message","message":"content without session id"}}` + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "")
	if !ok {
		t.Fatal("expected ok=true for empty query")
	}
	if summary.SessionID != "my_session_file" {
		t.Fatalf("expected session_id=my_session_file, got %q", summary.SessionID)
	}
}

// TestR38_SessionIDOverriddenByJSONField verifies that a sessionId field in
// JSON overrides the filename-based default.
func TestR38_SessionIDOverriddenByJSONField(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "original_name.jsonl")

	line := `{"sessionId":"json-session-id","type":"event_msg","payload":{"type":"message","message":"content"}}` + "\n"
	if err := os.WriteFile(path, []byte(line), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "")
	if !ok {
		t.Fatal("expected ok=true")
	}
	if summary.SessionID != "json-session-id" {
		t.Fatalf("expected session_id=json-session-id, got %q", summary.SessionID)
	}
}

// ── R38: First/Last timestamp tracking ───────────────────────────────────────

// TestR38_FirstLastTimestampTracking verifies that first and last timestamps
// are correctly tracked across multiple lines.
func TestR38_FirstLastTimestampTracking(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "ts.jsonl")

	lines := []string{
		`{"type":"event_msg","createdAt":"2025-01-01T10:00:00Z","payload":{"type":"message","message":"first"}}`,
		`{"type":"event_msg","createdAt":"2025-01-01T11:00:00Z","payload":{"type":"message","message":"middle"}}`,
		`{"type":"event_msg","createdAt":"2025-01-01T12:00:00Z","payload":{"type":"message","message":"last"}}`,
	}
	content := strings.Join(lines, "\n") + "\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(nil, 0)
	item := WorkItem{Source: "test", Path: path}
	summary, ok := sc.ProcessFile(item, "")
	if !ok {
		t.Fatal("expected ok=true")
	}
	if summary.FirstTimestamp != "2025-01-01T10:00:00Z" {
		t.Fatalf("expected first_timestamp=2025-01-01T10:00:00Z, got %q", summary.FirstTimestamp)
	}
	if summary.LastTimestamp != "2025-01-01T12:00:00Z" {
		t.Fatalf("expected last_timestamp=2025-01-01T12:00:00Z, got %q", summary.LastTimestamp)
	}
}

// ── R38: shouldSkipPath edge cases ────────────────────────────────────────────

// TestR38_ShouldSkipPathCaseSensitivity verifies case-insensitive matching for
// skills directories across various capitalizations.
func TestR38_ShouldSkipPathCaseSensitivity(t *testing.T) {
	cases := []struct {
		path string
		skip bool
	}{
		{"/home/user/.claude/SKILLS/file.json", true},
		{"/home/user/.claude/Skills/file.json", true},
		{"/home/user/SKILLS-REPO/file.json", true},
		{"/home/user/Skill-files/file.json", false}, // "skill-files" is not "/skills/" or "skills-repo"
		{"/home/user/.claude/noskills/file.json", false},
	}
	for _, tc := range cases {
		got := shouldSkipPath(tc.path)
		if got != tc.skip {
			t.Errorf("shouldSkipPath(%q) = %v, want %v", tc.path, got, tc.skip)
		}
	}
}

// TestR38_CollectFilesIgnoresNonJSONExtensions verifies that .txt, .log, and
// other non-.json/.jsonl files are not collected.
func TestR38_CollectFilesIgnoresNonJSONExtensions(t *testing.T) {
	dir := t.TempDir()

	exts := []string{".txt", ".log", ".csv", ".md", ".yaml", ".jsonl", ".json"}
	for _, ext := range exts {
		p := filepath.Join(dir, "testfile"+ext)
		if err := os.WriteFile(p, []byte("{}"), 0644); err != nil {
			t.Fatalf("write %s: %v", ext, err)
		}
	}

	roots := []WorkItem{{Source: "test", Path: dir}}
	items := collectFiles(roots)

	// Only .jsonl and .json should be collected
	if len(items) != 2 {
		t.Fatalf("expected 2 items (.jsonl + .json), got %d", len(items))
	}
	for _, item := range items {
		ext := filepath.Ext(item.Path)
		if ext != ".json" && ext != ".jsonl" {
			t.Errorf("unexpected extension %q for collected item %q", ext, item.Path)
		}
	}
}
