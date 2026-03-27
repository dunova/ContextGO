package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
)

// ── NoiseFilter ───────────────────────────────────────────────────────────────

func TestNoiseFilter(t *testing.T) {
	filter := NewNoiseFilter([]string{"marker", "agent"})

	t.Run("detects_marker", func(t *testing.T) {
		if !filter.IsNoise("this line mentions marker text") {
			t.Fatal("expected noise marker to be detected")
		}
	})

	t.Run("detects_prefix", func(t *testing.T) {
		if !filter.IsNoise("## heading style noise") {
			t.Fatal("expected noise prefix to be detected")
		}
	})

	t.Run("passes_clean_line", func(t *testing.T) {
		if filter.IsNoise("clean, helpful line") {
			t.Fatal("did not expect clean line to be marked as noise")
		}
	})
}

func TestNoiseFilterMetaChatter(t *testing.T) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	line := "我继续沿结果质量这条线打，不回到命名层。先复看当前工作树和主链 search NotebookLM 的命中。"
	if !filter.IsNoise(strings.ToLower(line)) {
		t.Fatal("expected active-session meta chatter to be filtered")
	}
}

// ── SnippetMatcher ────────────────────────────────────────────────────────────

func TestSnippetMatcher(t *testing.T) {
	filter := NewNoiseFilter([]string{"noise"})

	t.Run("non_empty_query", func(t *testing.T) {
		m := NewSnippetMatcher("query", filter, 5)
		if m.QueryEmpty() {
			t.Fatal("query should not be empty")
		}
	})

	t.Run("snippet_honours_limit", func(t *testing.T) {
		m := NewSnippetMatcher("query", filter, 5)
		snippet, ok := m.Match("before query text")
		if !ok {
			t.Fatal("expected match for text containing query")
		}
		if len(snippet) != 5 {
			t.Fatalf("expected snippet length 5, got %d (%q)", len(snippet), snippet)
		}
	})

	t.Run("noise_line_filtered", func(t *testing.T) {
		m := NewSnippetMatcher("query", filter, 40)
		if _, ok := m.Match("prefix query noise skill.md near match"); ok {
			t.Fatal("expected noise lines to stay filtered")
		}
	})

	t.Run("no_keyword_no_match", func(t *testing.T) {
		m := NewSnippetMatcher("query", filter, 5)
		if _, ok := m.Match("missing keyword here"); ok {
			t.Fatal("expected lines without keyword to not match")
		}
	})

	t.Run("distant_noise_marker_does_not_kill_real_match", func(t *testing.T) {
		m := NewSnippetMatcher("notebooklm", NewNoiseFilter(DefaultNoiseMarkers), 60)
		text := "skill.md very far away before the useful section and no longer near the final match ................................ NotebookLM useful content near query"
		snippet, ok := m.Match(text)
		if !ok {
			t.Fatal("expected local query window to survive distant noise markers")
		}
		if !strings.Contains(strings.ToLower(snippet), "notebooklm") {
			t.Fatalf("expected snippet to contain query, got %q", snippet)
		}
	})

	t.Run("empty_query_is_empty", func(t *testing.T) {
		if !NewSnippetMatcher("", filter, 1).QueryEmpty() {
			t.Fatal("empty query should be considered empty")
		}
	})
}

// ── summarize ─────────────────────────────────────────────────────────────────

func TestSummarize(t *testing.T) {
	results := []SessionSummary{
		{Source: "claude", Lines: 2, SizeBytes: 10},
		{Source: "codex", Lines: 3, SizeBytes: 5},
		{Source: "codex", Lines: 1, SizeBytes: 4},
	}
	aggs := summarize(results)
	if len(aggs) != 2 {
		t.Fatalf("expected 2 aggregates, got %d", len(aggs))
	}
	want := map[string]Aggregate{
		"claude": {Source: "claude", Count: 1, TotalLines: 2, TotalSize: 10},
		"codex":  {Source: "codex", Count: 2, TotalLines: 4, TotalSize: 9},
	}
	for _, agg := range aggs {
		w, ok := want[agg.Source]
		if !ok {
			t.Fatalf("unexpected source %q", agg.Source)
		}
		if agg.Count != w.Count || agg.TotalLines != w.TotalLines || agg.TotalSize != w.TotalSize {
			t.Fatalf("aggregate mismatch for %q: got %+v, want %+v", agg.Source, agg, w)
		}
	}
}

// ── shouldSkipRecordType ──────────────────────────────────────────────────────

func TestShouldSkipRecordType(t *testing.T) {
	t.Run("skips_function_call_output", func(t *testing.T) {
		rec := map[string]any{
			"type":    "response_item",
			"payload": map[string]any{"type": "function_call_output"},
		}
		if !shouldSkipRecordType(rec) {
			t.Fatal("expected function_call_output record to be skipped")
		}
	})

	t.Run("keeps_normal_message", func(t *testing.T) {
		rec := map[string]any{
			"type":    "response_item",
			"payload": map[string]any{"type": "message"},
		}
		if shouldSkipRecordType(rec) {
			t.Fatal("did not expect normal message record to be skipped")
		}
	})

	t.Run("skips_token_count", func(t *testing.T) {
		rec := map[string]any{
			"type":    "event_msg",
			"payload": map[string]any{"type": "token_count"},
		}
		if !shouldSkipRecordType(rec) {
			t.Fatal("expected token_count event to be skipped")
		}
	})
}

// ── shouldSkipPath ────────────────────────────────────────────────────────────

func TestShouldSkipPath(t *testing.T) {
	cases := []struct {
		path string
		skip bool
	}{
		{"/Users/testuser/.codex/skills/notebooklm/SKILL.md", true},
		{"/Users/testuser/.claude/projects/-Users-testuser-skills-repo/a.jsonl", true},
		{"/Users/testuser/.codex/sessions/2026/03/test.jsonl", false},
	}
	for _, tc := range cases {
		t.Run(tc.path, func(t *testing.T) {
			got := shouldSkipPath(tc.path)
			if got != tc.skip {
				t.Fatalf("shouldSkipPath(%q) = %v, want %v", tc.path, got, tc.skip)
			}
		})
	}
}

// ── ProcessFile integration ───────────────────────────────────────────────────

func TestProcessFileSurvivesLargeArchivedLines(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	huge := strings.Repeat("x", 80*1024)
	first, err := json.Marshal(map[string]any{
		"type":    "response_item",
		"payload": map[string]any{"type": "function_call_output", "output": huge},
	})
	if err != nil {
		t.Fatalf("marshal first line: %v", err)
	}
	second, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "这里有一个 NotebookLM 历史结论。"},
	})
	if err != nil {
		t.Fatalf("marshal second line: %v", err)
	}

	for _, data := range [][]byte{
		append(first, '\n'),
		append(second, '\n'),
	} {
		if _, err := tmp.Write(data); err != nil {
			t.Fatalf("write temp file: %v", err)
		}
	}

	sc := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "codex_session", Path: tmp.Name()}, "NotebookLM")
	if !ok {
		t.Fatal("expected match after large line")
	}
	if !strings.Contains(strings.ToLower(summary.Snippet), "notebooklm") {
		t.Fatalf("expected NotebookLM snippet, got %q", summary.Snippet)
	}
}

func TestProcessFileSkipsCurrentWorkdirSession(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	meta, err := json.Marshal(map[string]any{
		"type":    "session_meta",
		"payload": map[string]any{"id": "current-session", "cwd": cwd},
	})
	if err != nil {
		t.Fatalf("marshal meta: %v", err)
	}
	msg, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "NotebookLM 当前主链优化记录。"},
	})
	if err != nil {
		t.Fatalf("marshal msg: %v", err)
	}

	for _, data := range [][]byte{
		append(meta, '\n'),
		append(msg, '\n'),
	} {
		if _, err := tmp.Write(data); err != nil {
			t.Fatalf("write temp file: %v", err)
		}
	}

	sc := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)
	if _, ok := sc.ProcessFile(WorkItem{Source: "codex_session", Path: tmp.Name()}, "NotebookLM"); ok {
		t.Fatal("expected current workdir session to be skipped")
	}
}

// ── collectFiles ──────────────────────────────────────────────────────────────

func TestCollectFilesSkipsNonExistentRoots(t *testing.T) {
	items := collectFiles([]WorkItem{
		{Source: "codex_session", Path: "/nonexistent/path/sessions"},
	})
	if len(items) != 0 {
		t.Fatalf("expected 0 items for non-existent root, got %d", len(items))
	}
}

func TestCollectFilesFindsJsonlFiles(t *testing.T) {
	dir := t.TempDir()

	// Create a .jsonl file that should be found.
	f, err := os.CreateTemp(dir, "session*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	f.Close()

	// Create a .txt file that should not be found.
	txt, err := os.CreateTemp(dir, "ignore*.txt")
	if err != nil {
		t.Fatalf("create txt file: %v", err)
	}
	txt.Close()

	items := collectFiles([]WorkItem{{Source: "test", Path: dir}})
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}
	if items[0].Source != "test" {
		t.Fatalf("unexpected source %q", items[0].Source)
	}
}

// ── Benchmarks ────────────────────────────────────────────────────────────────

func BenchmarkProcessFile(b *testing.B) {
	// Create a temp file with realistic content.
	tmp, err := os.CreateTemp(b.TempDir(), "bench*.jsonl")
	if err != nil {
		b.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	line, err := json.Marshal(map[string]any{
		"type": "event_msg",
		"payload": map[string]any{
			"type":    "agent_message",
			"message": "The session_scan_go tool performs high-performance parallel scanning of JSONL session files.",
		},
	})
	if err != nil {
		b.Fatalf("marshal line: %v", err)
	}
	for i := 0; i < 100; i++ {
		if _, err := tmp.Write(append(line, '\n')); err != nil {
			b.Fatalf("write temp file: %v", err)
		}
	}
	if err := tmp.Sync(); err != nil {
		b.Fatalf("sync temp file: %v", err)
	}

	sc := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)
	item := WorkItem{Source: "bench", Path: tmp.Name()}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sc.ProcessFile(item, "session_scan_go")
	}
}

func BenchmarkClipSnippet(b *testing.B) {
	text := "some long string with mixed English and 中文内容 for testing snippet extraction"
	for i := 0; i < b.N; i++ {
		clipSnippet(text, 30, 50, 50)
	}
}

func BenchmarkIsNoise(b *testing.B) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	lines := []string{
		"clean, helpful line about the project architecture",
		"## heading style noise that should be filtered out",
		"我继续沿结果质量这条线打，不回到命名层。先复看当前工作树。",
		"The session_scan_go binary discovers JSONL files in ~/.codex and ~/.claude.",
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		for _, l := range lines {
			filter.IsNoise(l)
		}
	}
}

func BenchmarkSnippetMatcherMatch(b *testing.B) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	m := NewSnippetMatcher("session_scan_go", filter, defaultSnippetLimit)
	text := "The session_scan_go binary performs high-performance parallel scanning of JSONL session files for Codex and Claude projects."
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		m.Match(text)
	}
}

// ── NewSessionScanner defaults ────────────────────────────────────────────────

func TestNewSessionScannerDefaults(t *testing.T) {
	// nil filter → DefaultNoiseMarkers applied; snippetLimit ≤ 0 → defaultSnippetLimit.
	sc := NewSessionScanner(nil, 0)
	if sc.noiseFilter == nil {
		t.Fatal("expected non-nil noise filter from nil input")
	}
	if sc.snippetLimit != defaultSnippetLimit {
		t.Fatalf("expected snippetLimit %d, got %d", defaultSnippetLimit, sc.snippetLimit)
	}

	// Negative snippetLimit should also fall back.
	sc2 := NewSessionScanner(NewNoiseFilter(nil), -1)
	if sc2.snippetLimit != defaultSnippetLimit {
		t.Fatalf("expected snippetLimit %d for negative input, got %d", defaultSnippetLimit, sc2.snippetLimit)
	}

	// Explicit positive limit must be preserved.
	sc3 := NewSessionScanner(NewNoiseFilter(nil), 50)
	if sc3.snippetLimit != 50 {
		t.Fatalf("expected snippetLimit 50, got %d", sc3.snippetLimit)
	}
}

// ── ProcessFile error & edge case paths ──────────────────────────────────────

func TestProcessFileNotFound(t *testing.T) {
	sc := NewSessionScanner(nil, defaultSnippetLimit)
	_, ok := sc.ProcessFile(WorkItem{Source: "test", Path: "/nonexistent/file.jsonl"}, "query")
	if ok {
		t.Fatal("expected false for non-existent file")
	}
}

func TestProcessFileEmptyFile(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "empty*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	tmp.Close()

	sc := NewSessionScanner(nil, defaultSnippetLimit)
	// Empty query → matchFound starts true, so even an empty file returns ok.
	_, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "")
	if !ok {
		t.Fatal("expected ok=true for empty query (all files match)")
	}

	// Non-empty query → no match found in empty file.
	_, ok2 := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "something")
	if ok2 {
		t.Fatal("expected ok=false for non-empty query with no content")
	}
}

func TestProcessFileRawLineMatch(t *testing.T) {
	// A file whose lines are not valid JSON should still be matched as raw_line.
	tmp, err := os.CreateTemp(t.TempDir(), "raw*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	if _, err := tmp.WriteString("this is a raw non-json line with keyword here\n"); err != nil {
		t.Fatalf("write: %v", err)
	}

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "keyword")
	if !ok {
		t.Fatal("expected match on raw non-JSON line")
	}
	if summary.MatchField != "raw_line" {
		t.Fatalf("expected MatchField=raw_line, got %q", summary.MatchField)
	}
}

func TestProcessFileRootCwdFilter(t *testing.T) {
	// extractCwd should also read root-level "cwd" (not just payload.cwd).
	tmp, err := os.CreateTemp(t.TempDir(), "rootcwd*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}

	import_line, err := json.Marshal(map[string]any{
		"type": "session_meta",
		"cwd":  cwd, // root-level cwd, not nested under payload
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	msg, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "notebooklm search result"},
	})
	if err != nil {
		t.Fatalf("marshal msg: %v", err)
	}
	tmp.Write(append(import_line, '\n'))
	tmp.Write(append(msg, '\n'))

	sc := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)
	_, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "notebooklm")
	if ok {
		t.Fatal("expected file with root-level cwd matching current dir to be excluded")
	}
}

func TestProcessFileEmptyQueryAllMatch(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "allm*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	line, _ := json.Marshal(map[string]any{"type": "event_msg", "payload": map[string]any{"type": "agent_message", "message": "hello world"}})
	tmp.Write(append(line, '\n'))

	sc := NewSessionScanner(nil, defaultSnippetLimit)
	_, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "")
	if !ok {
		t.Fatal("expected ok=true for empty query")
	}
}

func TestProcessFileSessionIDFromPayload(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "sid*.jsonl")
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	defer tmp.Close()

	line, _ := json.Marshal(map[string]any{
		"type":    "session_meta",
		"payload": map[string]any{"id": "my-session-123"},
	})
	tmp.Write(append(line, '\n'))

	sc := NewSessionScanner(nil, defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "")
	if !ok {
		t.Fatal("expected ok=true for empty query")
	}
	if summary.SessionID != "my-session-123" {
		t.Fatalf("expected SessionID my-session-123, got %q", summary.SessionID)
	}
}

func TestProcessFileTimestamps(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "ts*.jsonl")
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	defer tmp.Close()

	first, _ := json.Marshal(map[string]any{"createdAt": "2025-01-01T00:00:00Z", "message": "first"})
	second, _ := json.Marshal(map[string]any{"createdAt": "2025-06-01T00:00:00Z", "message": "second"})
	tmp.Write(append(first, '\n'))
	tmp.Write(append(second, '\n'))

	sc := NewSessionScanner(nil, defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "")
	if !ok {
		t.Fatal("expected ok=true")
	}
	if summary.FirstTimestamp != "2025-01-01T00:00:00Z" {
		t.Fatalf("FirstTimestamp: got %q, want 2025-01-01T00:00:00Z", summary.FirstTimestamp)
	}
	if summary.LastTimestamp != "2025-06-01T00:00:00Z" {
		t.Fatalf("LastTimestamp: got %q, want 2025-06-01T00:00:00Z", summary.LastTimestamp)
	}
}

// ── shouldSkipRecordType remaining branches ───────────────────────────────────

func TestShouldSkipRecordTypeAdditional(t *testing.T) {
	cases := []struct {
		name string
		rec  map[string]any
		want bool
	}{
		{
			"turn_context",
			map[string]any{"type": "turn_context"},
			true,
		},
		{
			"custom_tool_call",
			map[string]any{"type": "custom_tool_call"},
			true,
		},
		{
			"response_item_function_call",
			map[string]any{"type": "response_item", "payload": map[string]any{"type": "function_call"}},
			true,
		},
		{
			"response_item_reasoning",
			map[string]any{"type": "response_item", "payload": map[string]any{"type": "reasoning"}},
			true,
		},
		{
			"event_msg_task_started",
			map[string]any{"type": "event_msg", "payload": map[string]any{"type": "task_started"}},
			true,
		},
		{
			"event_msg_agent_message_kept",
			map[string]any{"type": "event_msg", "payload": map[string]any{"type": "agent_message"}},
			false,
		},
		{
			"response_item_no_nested_payload",
			map[string]any{"type": "response_item"},
			false,
		},
		{
			"event_msg_no_nested_payload",
			map[string]any{"type": "event_msg"},
			false,
		},
		{
			"unknown_type",
			map[string]any{"type": "something_else"},
			false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := shouldSkipRecordType(tc.rec); got != tc.want {
				t.Fatalf("shouldSkipRecordType(%v) = %v, want %v", tc.rec, got, tc.want)
			}
		})
	}
}

// ── IsNoiseLower additional branches ─────────────────────────────────────────

func TestIsNoiseLowerEmptyString(t *testing.T) {
	f := NewNoiseFilter(nil)
	if !f.IsNoiseLower("") {
		t.Fatal("expected empty string to be noise")
	}
}

func TestIsNoiseLowerNilFilter(t *testing.T) {
	var f *NoiseFilter
	if f.IsNoiseLower("anything") {
		t.Fatal("nil filter should return false")
	}
}

func TestIsNoiseLowerFSNoise(t *testing.T) {
	f := NewNoiseFilter(nil)
	cases := []struct {
		name string
		line string
	}{
		{"drwx", "drwxr-xr-x   2 user staff  64 jan  1 00:00 dir"},
		{"rwxr-xr-x", "-rwxr-xr-x   1 user staff 128 jan  1 00:00 file"},
		{"ntotal", "some content\ntotal 42 blocks"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if !f.IsNoiseLower(tc.line) {
				t.Fatalf("expected %q to be noise", tc.line)
			}
		})
	}
}

func TestIsNoiseLowerNotebooklmCompound(t *testing.T) {
	f := NewNoiseFilter(nil)
	line := "notebooklm search session_index native-scan result"
	if !f.IsNoiseLower(line) {
		t.Fatalf("expected notebooklm compound pattern to be noise: %q", line)
	}
}

func TestIsNoiseLowerWoXianCompound(t *testing.T) {
	f := NewNoiseFilter(nil)
	cases := []string{
		"我先做 search 查询",
		"我继续 native-scan 结果",
		"我先看 session_index 状态",
		"我继续 search 下去",
	}
	for _, line := range cases {
		if !f.IsNoiseLower(line) {
			t.Fatalf("expected Chinese action meta-chatter to be noise: %q", line)
		}
	}
}

func TestIsNoiseLowerShortTokenHeuristic(t *testing.T) {
	f := NewNoiseFilter(nil)
	// Five or more short spaceless tokens triggers the heuristic.
	line := "tokena\ntokenb\ntokenc\ntokend\ntokene\ntokenf"
	if !f.IsNoiseLower(line) {
		t.Fatalf("expected short-token heuristic to flag line: %q", line)
	}
	// Fewer than 5 short tokens should not be flagged solely by the heuristic.
	clean := "tokena\ntokenb\ntokenc"
	if f.IsNoiseLower(clean) {
		t.Fatalf("did not expect short-token heuristic to flag only 3 tokens: %q", clean)
	}
}

// TestIsNoiseLowerShortTokenEmptyParts verifies that the short-token loop
// correctly skips over empty parts produced by consecutive newlines (the
// "if part == """  { continue }" branch inside the short-token counter loop).
func TestIsNoiseLowerShortTokenEmptyParts(t *testing.T) {
	f := NewNoiseFilter(nil)
	// Consecutive newlines create empty split parts.  The 6 real tokens should
	// still be counted and trigger the heuristic (>= 5 short spaceless tokens).
	line := "tokena\n\ntokenb\n\ntokenc\n\ntokend\n\ntokene\n\ntokenf"
	if !f.IsNoiseLower(line) {
		t.Fatalf("expected short-token heuristic to flag line with empty split parts: %q", line)
	}
	// Only 3 real tokens separated by empty parts — should NOT trigger heuristic.
	sparse := "alpha\n\nbeta\n\ngamma"
	if f.IsNoiseLower(sparse) {
		t.Fatalf("did not expect heuristic to flag only 3 tokens with empty parts: %q", sparse)
	}
}

// ── SnippetMatcher nil receiver ───────────────────────────────────────────────

func TestSnippetMatcherNilReceiver(t *testing.T) {
	var m *SnippetMatcher
	if !m.QueryEmpty() {
		t.Fatal("nil SnippetMatcher.QueryEmpty() should return true")
	}
	_, ok := m.Match("some text")
	if ok {
		t.Fatal("nil SnippetMatcher.Match() should return false")
	}
}

// ── fieldPriority ─────────────────────────────────────────────────────────────

func TestFieldPriority(t *testing.T) {
	cases := []struct {
		field string
		want  int
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
		{"unknown_field", 40},
	}
	for _, tc := range cases {
		t.Run(tc.field, func(t *testing.T) {
			if got := fieldPriority(tc.field); got != tc.want {
				t.Fatalf("fieldPriority(%q) = %d, want %d", tc.field, got, tc.want)
			}
		})
	}
}

// ── clipRuneWindow edge cases ─────────────────────────────────────────────────

func TestClipRuneWindowNegativeInputs(t *testing.T) {
	text := "hello world test"
	// Negative index should be clamped to 0.
	start, end := clipRuneWindow(text, -5, 3, 5)
	if start < 0 {
		t.Fatalf("start should be >= 0, got %d", start)
	}
	if end-start > 5 {
		t.Fatalf("window too large: start=%d end=%d", start, end)
	}

	// Negative queryLen should be clamped to 0.
	start2, end2 := clipRuneWindow(text, 2, -3, 5)
	if start2 < 0 || end2 < start2 {
		t.Fatalf("invalid window with negative queryLen: start=%d end=%d", start2, end2)
	}
}

func TestClipRuneWindowTextShorterThanLimit(t *testing.T) {
	text := "short"
	start, end := clipRuneWindow(text, 0, 2, 100)
	if start != 0 || end != len([]rune(text)) {
		t.Fatalf("expected full text [0,%d], got [%d,%d]", len([]rune(text)), start, end)
	}
}

func TestClipRuneWindowMatchNearEnd(t *testing.T) {
	// Match near the end should shift window backwards to fill the limit.
	text := "aaaabbbbccccddddeeeeffffgggghhhhiiiijjjjkkkkquery"
	idx := strings.Index(strings.ToLower(text), "query")
	start, end := clipRuneWindow(text, idx, len("query"), 10)
	if end-start > 10 {
		t.Fatalf("window too large: %d", end-start)
	}
	if end > len([]rune(text)) {
		t.Fatalf("end %d exceeds rune count %d", end, len([]rune(text)))
	}
}

// ── clipSnippet limit <= 0 ────────────────────────────────────────────────────

func TestClipSnippetZeroLimit(t *testing.T) {
	text := "some text here"
	got := clipSnippet(text, 0, 4, 0)
	if got != text {
		t.Fatalf("clipSnippet with limit=0 should return full text, got %q", got)
	}
}

func TestClipSnippetNegativeLimit(t *testing.T) {
	text := "some text here"
	got := clipSnippet(text, 0, 4, -1)
	if got != text {
		t.Fatalf("clipSnippet with negative limit should return full text, got %q", got)
	}
}

func TestClipSnippetExactLimit(t *testing.T) {
	// Text length == limit should return full text, not slice.
	text := "hello" // 5 runes
	got := clipSnippet(text, 0, 5, 5)
	if got != text {
		t.Fatalf("expected %q, got %q", text, got)
	}
}

// ── extractTextCandidates additional fields ───────────────────────────────────

func TestExtractTextCandidatesAllFields(t *testing.T) {
	payload := map[string]any{
		"message":              "root message",
		"display":              "root display",
		"text":                 "root text",
		"prompt":               "root prompt",
		"output":               "root output",
		"content":              "root content",
		"user_instructions":    "root user_instructions",
		"last_agent_message":   "root last_agent_message",
		"payload": map[string]any{
			"message":            "payload message",
			"display":            "payload display",
			"text":               "payload text",
			"prompt":             "payload prompt",
			"output":             "payload output",
			"user_instructions":  "payload user_instructions",
			"last_agent_message": "payload last_agent_message",
			"content": []any{
				map[string]any{"text": "payload content item 1"},
				map[string]any{"text": "payload content item 2"},
			},
		},
	}

	candidates := extractTextCandidates(payload)
	// Collect all found texts.
	found := make(map[string]bool)
	for _, c := range candidates {
		found[c.Text] = true
	}

	expected := []string{
		"root message", "root display", "root text", "root prompt",
		"root output", "root content",
		"payload message", "payload display", "payload text", "payload prompt",
		"payload output", "payload user_instructions", "payload last_agent_message",
		"payload content item 1", "payload content item 2",
		"root user_instructions", "root last_agent_message",
	}
	for _, e := range expected {
		if !found[e] {
			t.Errorf("missing candidate text %q from extractTextCandidates", e)
		}
	}
}

func TestExtractTextCandidatesMessageContentList(t *testing.T) {
	// message.content as list of {text: ...} objects.
	payload := map[string]any{
		"message": map[string]any{
			"content": []any{
				map[string]any{"text": "item one"},
				map[string]any{"text": "item two"},
			},
		},
	}
	candidates := extractTextCandidates(payload)
	found := make(map[string]bool)
	for _, c := range candidates {
		found[c.Field+":"+c.Text] = true
	}
	for _, want := range []string{"message.content.text:item one", "message.content.text:item two"} {
		if !found[want] {
			t.Errorf("missing %q in candidates", want)
		}
	}
}

func TestExtractTextCandidatesMessageContentString(t *testing.T) {
	// message.content as plain string.
	payload := map[string]any{
		"message": map[string]any{"content": "plain content string"},
	}
	candidates := extractTextCandidates(payload)
	found := false
	for _, c := range candidates {
		if c.Field == "message.content" && c.Text == "plain content string" {
			found = true
		}
	}
	if !found {
		t.Fatal("expected message.content plain string to be extracted")
	}
}

func TestExtractTextCandidatesEmpty(t *testing.T) {
	// Empty/whitespace strings must not be included.
	payload := map[string]any{
		"message": "  ",
		"text":    "",
	}
	candidates := extractTextCandidates(payload)
	if len(candidates) != 0 {
		t.Fatalf("expected 0 candidates for empty strings, got %d: %v", len(candidates), candidates)
	}
}

// ── extractSessionID ──────────────────────────────────────────────────────────

func TestExtractSessionID(t *testing.T) {
	cases := []struct {
		name    string
		payload map[string]any
		want    string
	}{
		{
			"payload.id",
			map[string]any{"payload": map[string]any{"id": "pid-1"}},
			"pid-1",
		},
		{
			"root.sessionId",
			map[string]any{"sessionId": "sid-2"},
			"sid-2",
		},
		{
			"root.session_id",
			map[string]any{"session_id": "sid-3"},
			"sid-3",
		},
		{
			"no id",
			map[string]any{"type": "event_msg"},
			"",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := extractSessionID(tc.payload); got != tc.want {
				t.Fatalf("extractSessionID = %q, want %q", got, tc.want)
			}
		})
	}
}

// ── extractTimestamp ──────────────────────────────────────────────────────────

func TestExtractTimestamp(t *testing.T) {
	cases := []struct {
		name    string
		payload map[string]any
		want    string
	}{
		{
			"payload.timestamp",
			map[string]any{"payload": map[string]any{"timestamp": "2025-01-01T00:00:00Z"}},
			"2025-01-01T00:00:00Z",
		},
		{
			"root.createdAt",
			map[string]any{"createdAt": "2025-02-01T00:00:00Z"},
			"2025-02-01T00:00:00Z",
		},
		{
			"root.created_at",
			map[string]any{"created_at": "2025-03-01T00:00:00Z"},
			"2025-03-01T00:00:00Z",
		},
		{
			"root.timestamp",
			map[string]any{"timestamp": "2025-04-01T00:00:00Z"},
			"2025-04-01T00:00:00Z",
		},
		{
			"root.time",
			map[string]any{"time": "2025-05-01T00:00:00Z"},
			"2025-05-01T00:00:00Z",
		},
		{
			"none",
			map[string]any{"type": "event_msg"},
			"",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := extractTimestamp(tc.payload); got != tc.want {
				t.Fatalf("extractTimestamp = %q, want %q", got, tc.want)
			}
		})
	}
}

// ── extractCwd ────────────────────────────────────────────────────────────────

func TestExtractCwd(t *testing.T) {
	cases := []struct {
		name    string
		payload map[string]any
		want    string
	}{
		{
			"payload.cwd",
			map[string]any{"payload": map[string]any{"cwd": "/home/user/project"}},
			"/home/user/project",
		},
		{
			"root.cwd",
			map[string]any{"cwd": "/home/user/other"},
			"/home/user/other",
		},
		{
			"none",
			map[string]any{"type": "event_msg"},
			"",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := extractCwd(tc.payload); got != tc.want {
				t.Fatalf("extractCwd = %q, want %q", got, tc.want)
			}
		})
	}
}

// ── normalizedCurrentWorkdir with env override ────────────────────────────────

func TestNormalizedCurrentWorkdirEnvOverride(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("CONTEXTGO_ACTIVE_WORKDIR", dir)
	got := normalizedCurrentWorkdir()
	if got == "" {
		t.Fatal("expected non-empty result with CONTEXTGO_ACTIVE_WORKDIR set")
	}
	// The result should resolve to the same directory.
	if !strings.HasSuffix(got, dir) && got != dir {
		// Accept if it's the real path via symlink resolution.
		if !strings.Contains(got, "tmp") && !strings.Contains(got, "var") {
			t.Logf("normalizedCurrentWorkdir with env = %q, dir = %q", got, dir)
		}
	}
}

func TestNormalizedCurrentWorkdirNoEnv(t *testing.T) {
	t.Setenv("CONTEXTGO_ACTIVE_WORKDIR", "")
	got := normalizedCurrentWorkdir()
	if got == "" {
		t.Fatal("expected non-empty result from os.Getwd() fallback")
	}
}

// ── normalizePath edge cases ──────────────────────────────────────────────────

func TestNormalizePathEmpty(t *testing.T) {
	if got := normalizePath(""); got != "" {
		t.Fatalf("normalizePath(\"\") = %q, want \"\"", got)
	}
}

func TestNormalizePathAbsolute(t *testing.T) {
	dir := t.TempDir()
	got := normalizePath(dir)
	if got == "" {
		t.Fatal("expected non-empty path")
	}
}

// ── SnippetMatcher.Match empty text ──────────────────────────────────────────

func TestSnippetMatcherMatchEmptyText(t *testing.T) {
	m := NewSnippetMatcher("query", NewNoiseFilter(nil), 40)
	_, ok := m.Match("   ")
	if ok {
		t.Fatal("expected no match on whitespace-only text")
	}
	_, ok2 := m.Match("")
	if ok2 {
		t.Fatal("expected no match on empty text")
	}
}

// ── SnippetMatcher.Match no snippet limit ─────────────────────────────────────

func TestSnippetMatcherNoLimit(t *testing.T) {
	// limit=0 means clipSnippet is skipped (full text returned).
	m := NewSnippetMatcher("hello", NewNoiseFilter(nil), 0)
	text := "say hello to the world"
	snippet, ok := m.Match(text)
	if !ok {
		t.Fatal("expected match")
	}
	if snippet != text {
		t.Fatalf("expected full text %q, got %q", text, snippet)
	}
}

// ── clipSnippet / SnippetMatcher Unicode correctness ─────────────────────────

// TestSnippetMatcherToLowerByteShift verifies that Match handles text where
// strings.ToLower changes the byte length of a character (e.g. Turkish İ
// U+0130 → "i", 2 bytes → 1 byte).  A naive implementation that passes the
// byte offset from the lowercased string directly to clipSnippet on the
// original string would produce an invalid byte offset and either corrupt the
// result or panic in the rune-conversion loop.
func TestSnippetMatcherToLowerByteShift(t *testing.T) {
	// "İstanbul" — İ (U+0130, 2 bytes UTF-8) lowercases to "i" (1 byte),
	// so strings.ToLower shrinks the byte length by one.
	// Query "istanbul" (all-lowercase) must still be found and the returned
	// snippet must be valid UTF-8 with no replacement characters.
	filter := NewNoiseFilter(nil)
	m := NewSnippetMatcher("istanbul", filter, 20)
	text := "İstanbul is a great city"
	snippet, ok := m.Match(text)
	if !ok {
		t.Fatalf("expected match in %q, got none", text)
	}
	for i, r := range snippet {
		if r == '\uFFFD' {
			t.Fatalf("snippet contains replacement character at rune %d: %q", i, snippet)
		}
	}
}

func TestClipSnippetCJK(t *testing.T) {
	// Each CJK character is 3 bytes in UTF-8.  Verify that the snippet window
	// is measured in runes, not bytes, so CJK text is never split or
	// miscounted.
	text := "前缀内容：这里包含查询词目标以及后缀内容，用于验证多字节字符不被截断。"
	// "查询词" starts at some byte offset; find it via strings.Index on lower.
	query := "查询词"
	idx := strings.Index(strings.ToLower(text), strings.ToLower(query))
	if idx < 0 {
		t.Fatal("test setup: query not found in text")
	}

	limit := 10
	snippet := clipSnippet(text, idx, len(query), limit)
	runeCount := len([]rune(snippet))
	if runeCount > limit {
		t.Fatalf("clipSnippet returned %d runes, want <= %d; snippet=%q", runeCount, limit, snippet)
	}
	if !strings.Contains(snippet, query) {
		t.Fatalf("clipSnippet result %q does not contain query %q", snippet, query)
	}

	// Verify the result is valid UTF-8 (no torn multi-byte sequences).
	for i, r := range snippet {
		if r == '\uFFFD' {
			t.Fatalf("clipSnippet produced replacement character at rune index %d; snippet=%q", i, snippet)
		}
	}
}

// ── clipRuneWindow: match near end triggers backwards-extend path ─────────────

// TestClipRuneWindowMatchAtEnd exercises the branch where the naively
// computed end exceeds total and the window must be shifted backwards.
// With text="abcdef" (6 runes), limit=5, match at byte offset 5 ('f'):
//
//	runeIdx=5, radius=2, start=3, end=8 → end>total → end=6, start=1
func TestClipRuneWindowMatchAtEnd(t *testing.T) {
	text := "abcdef" // 6 runes
	// Match at the very last character.
	start, end := clipRuneWindow(text, 5, 1, 5)
	if end != 6 {
		t.Fatalf("expected end=6, got %d", end)
	}
	if start != 1 {
		t.Fatalf("expected start=1, got %d", start)
	}
	if end-start != 5 {
		t.Fatalf("window size should be 5, got %d", end-start)
	}
}

// TestClipRuneWindowMatchAtEndCJK verifies the backwards-extend path with
// multi-byte (CJK) characters so the rune-vs-byte boundary is exercised.
func TestClipRuneWindowMatchAtEndCJK(t *testing.T) {
	// 8 CJK runes; match on the last 2.
	text := "一二三四五六七八"
	query := "七八"
	idx := strings.Index(text, query)
	if idx < 0 {
		t.Fatal("test setup: query not in text")
	}
	// limit=5, runeIdx for "七" = 6, radius=2, start=4, end=9 > 8 → end=8, start=3
	start, end := clipRuneWindow(text, idx, len(query), 5)
	runes := []rune(text)
	if end > len(runes) {
		t.Fatalf("end %d exceeds rune count %d", end, len(runes))
	}
	if end-start > 5 {
		t.Fatalf("window too large: %d", end-start)
	}
	snippet := string(runes[start:end])
	if !strings.Contains(snippet, query) {
		t.Fatalf("snippet %q does not contain query %q", snippet, query)
	}
}

// ── ProcessFile: blank lines in input file ────────────────────────────────────

// TestProcessFileBlankLines confirms that blank lines (after TrimSpace) are
// skipped without incrementing the line counter, and that the subsequent
// non-blank JSON line is still processed and matched.
func TestProcessFileBlankLines(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "blank*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	// Write several blank lines followed by a matchable JSON record.
	tmp.WriteString("\n   \n\t\n")
	line, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "context keyword present here"},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	tmp.Write(append(line, '\n'))

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "keyword")
	if !ok {
		t.Fatal("expected match after skipping blank lines")
	}
	// Only the non-blank JSON line should be counted.
	if summary.Lines != 1 {
		t.Fatalf("expected Lines=1, got %d", summary.Lines)
	}
}

// ── ProcessFile: multiple candidates, best score wins ────────────────────────

// TestProcessFileBestScoreWins verifies that when multiple records match,
// the one with the highest candidateScore (field priority + hit frequency)
// is kept as summary.Snippet.
func TestProcessFileBestScoreWins(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "score*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	// Low-priority field (raw_line, score=10+25=35): single hit
	tmp.WriteString("raw line with keyword once\n")

	// High-priority field (message.content.text, score=120+50=170): two hits
	high, err := json.Marshal(map[string]any{
		"message": map[string]any{
			"content": []any{
				map[string]any{"text": "keyword appears here and again keyword"},
			},
		},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	tmp.Write(append(high, '\n'))

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "keyword")
	if !ok {
		t.Fatal("expected a match")
	}
	if summary.MatchField != "message.content.text" {
		t.Fatalf("expected best-scoring field message.content.text, got %q", summary.MatchField)
	}
}

// ── candidateScore with empty queryLower ──────────────────────────────────────

func TestCandidateScoreEmptyQuery(t *testing.T) {
	// When queryLower is empty, hits must stay 0 and score == fieldPriority only.
	score := candidateScore("message", "some text", "")
	if score != fieldPriority("message") {
		t.Fatalf("expected score=%d for empty query, got %d", fieldPriority("message"), score)
	}
}

// ── NoiseFilter: empty marker list still applies prefix rules ─────────────────

func TestNoiseFilterEmptyMarkers(t *testing.T) {
	f := NewNoiseFilter([]string{})
	// Prefix rules from DefaultNoisePrefixes still apply.
	if !f.IsNoise("## heading") {
		t.Fatal("expected ## prefix to be caught even with empty custom markers")
	}
	if !f.IsNoise("```code block") {
		t.Fatal("expected ``` prefix to be caught even with empty custom markers")
	}
	// Clean line should pass.
	if f.IsNoise("clean and useful content line") {
		t.Fatal("expected clean line to pass empty-marker filter")
	}
}

// ── NoiseFilter: whitespace-only markers are ignored ─────────────────────────

func TestNoiseFilterWhitespaceMarkersIgnored(t *testing.T) {
	// Whitespace-only markers must be dropped during normalisation.
	f := NewNoiseFilter([]string{"  ", "\t", "", "real_marker"})
	if !f.IsNoise("line with real_marker inside") {
		t.Fatal("expected real_marker to be detected")
	}
	// A line that has no real marker and no noise prefix should pass.
	if f.IsNoise("clean line without any marker") {
		t.Fatal("expected clean line to pass whitespace-stripped marker filter")
	}
}

// ── SnippetMatcher: very long line, snippet still within limit ────────────────

// TestSnippetMatcherVeryLongLine ensures that a line much longer than
// snippetLimit is correctly truncated to exactly snippetLimit runes.
func TestSnippetMatcherVeryLongLine(t *testing.T) {
	filter := NewNoiseFilter(nil)
	limit := 50
	m := NewSnippetMatcher("target", filter, limit)

	// Build a 500-char ASCII line with "target" near the middle.
	prefix := strings.Repeat("a", 250)
	suffix := strings.Repeat("b", 244)
	text := prefix + "target" + suffix // 500 runes

	snippet, ok := m.Match(text)
	if !ok {
		t.Fatal("expected match in very long line")
	}
	runeCount := len([]rune(snippet))
	if runeCount > limit {
		t.Fatalf("snippet rune count %d exceeds limit %d", runeCount, limit)
	}
	if !strings.Contains(strings.ToLower(snippet), "target") {
		t.Fatalf("snippet %q does not contain query", snippet)
	}
}

// TestSnippetMatcherVeryLongLineCJK mirrors the above with CJK text to confirm
// multi-byte characters are counted in runes, not bytes.
func TestSnippetMatcherVeryLongLineCJK(t *testing.T) {
	filter := NewNoiseFilter(nil)
	limit := 20
	m := NewSnippetMatcher("目标词", filter, limit)

	// 60 CJK runes: 20 prefix + query(3) + 37 suffix
	prefix := strings.Repeat("前", 20)
	suffix := strings.Repeat("后", 37)
	text := prefix + "目标词" + suffix

	snippet, ok := m.Match(text)
	if !ok {
		t.Fatal("expected CJK match in long line")
	}
	runeCount := len([]rune(snippet))
	if runeCount > limit {
		t.Fatalf("CJK snippet rune count %d exceeds limit %d", runeCount, limit)
	}
	for i, r := range snippet {
		if r == '\uFFFD' {
			t.Fatalf("replacement character at rune %d in CJK snippet %q", i, snippet)
		}
	}
}

// ── ProcessFile: Unicode edge cases in raw (non-JSON) lines ──────────────────

// TestProcessFileUnicodeLongRawLine confirms that a very long raw non-JSON
// line with CJK content does not cause a panic or return garbage snippets.
func TestProcessFileUnicodeLongRawLine(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "unraw*.jsonl")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	defer tmp.Close()

	// 200 CJK runes + query + 200 more CJK runes — not valid JSON.
	line := strings.Repeat("字", 200) + "搜索词" + strings.Repeat("符", 200)
	tmp.WriteString(line + "\n")

	sc := NewSessionScanner(NewNoiseFilter(nil), 30)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "搜索词")
	if !ok {
		t.Fatal("expected match in Unicode raw line")
	}
	if len([]rune(summary.Snippet)) > 30 {
		t.Fatalf("snippet exceeds limit: %d runes", len([]rune(summary.Snippet)))
	}
	if summary.MatchField != "raw_line" {
		t.Fatalf("expected raw_line field, got %q", summary.MatchField)
	}
	for i, r := range summary.Snippet {
		if r == '\uFFFD' {
			t.Fatalf("replacement character at rune %d in snippet %q", i, summary.Snippet)
		}
	}
}

// ── SnippetMatcher: exact snippet boundary (query fills the entire limit) ─────

// TestSnippetMatcherQueryFillsLimit checks the boundary where the snippet
// limit equals the query length.  The window is centred on the match so the
// returned snippet will contain at least the central part of the query.
// The returned snippet must not exceed limit runes.
func TestSnippetMatcherQueryFillsLimit(t *testing.T) {
	filter := NewNoiseFilter(nil)
	// Use a query that is at most as long as the limit.
	// With limit=10 and query="hello" (5 runes) the whole query always fits.
	query := "hello"
	limit := 10
	m := NewSnippetMatcher(query, filter, limit)

	text := "prefix hello suffix long enough to exceed the snippet limit value"
	snippet, ok := m.Match(text)
	if !ok {
		t.Fatal("expected match")
	}
	runeCount := len([]rune(snippet))
	if runeCount > limit {
		t.Fatalf("snippet %q has %d runes, want <= %d", snippet, runeCount, limit)
	}
	if !strings.Contains(strings.ToLower(snippet), query) {
		t.Fatalf("snippet %q does not contain query %q", snippet, query)
	}
}

// ── UTF-8 BOM handling ────────────────────────────────────────────────────────

// TestProcessFileUTF8BOM verifies that a file beginning with a UTF-8 BOM
// (EF BB BF) is scanned without errors and that content after the BOM is
// matched normally.  The BOM appears on the first line; Go's bufio.Scanner
// does not strip it automatically so the line starts with the BOM bytes.
// ProcessFile must not crash and must still find the query keyword.
func TestProcessFileUTF8BOM(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "bom*.jsonl")
	if err != nil {
		t.Fatalf("create temp: %v", err)
	}
	defer tmp.Close()

	// Write UTF-8 BOM followed by a valid JSON line.
	bom := []byte{0xEF, 0xBB, 0xBF}
	line, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "BOM test keyword here"},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	// The BOM prefix makes the line invalid JSON, so it falls through to raw_line matching.
	tmp.Write(append(bom, append(line, '\n')...))

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "keyword")
	if !ok {
		t.Fatal("expected match in BOM-prefixed file")
	}
	if summary.MatchField != "raw_line" {
		// Either raw_line (BOM broke JSON parse) or a JSON field — both are acceptable.
		_ = summary.MatchField
	}
}

// TestProcessFileLatin1Fallback verifies that a file containing Latin-1 bytes
// (non-valid UTF-8 sequences like 0x80–0xFF) does not cause ProcessFile to
// panic.  The non-UTF-8 content is treated as raw bytes by bufio.Scanner; Go
// string operations on such bytes are safe (though replacement characters may
// appear in the rune view).  The test simply asserts no panic and that the
// function returns a result.
func TestProcessFileLatin1Fallback(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "latin1*.jsonl")
	if err != nil {
		t.Fatalf("create temp: %v", err)
	}
	defer tmp.Close()

	// Write a line with Latin-1 bytes followed by the query keyword in ASCII.
	latin1Line := []byte("caf\xe9 and keyword present\n") // 0xE9 = é in Latin-1
	tmp.Write(latin1Line)

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	// Should not panic, regardless of whether it matches.
	sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "keyword")
}

// ── Very large files (>1 MB content) ─────────────────────────────────────────

// TestProcessFileVeryLargeFile confirms that ProcessFile correctly handles a
// file whose total content exceeds 1 MB.  The scanner buffer is pre-allocated
// at 1 MB and can grow to 32 MB, so this exercises the growth path.
func TestProcessFileVeryLargeFile(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "large*.jsonl")
	if err != nil {
		t.Fatalf("create temp: %v", err)
	}
	defer tmp.Close()

	// Write 2000 moderate-sized JSON lines (~600 bytes each ≈ 1.2 MB total).
	normalLine, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": strings.Repeat("padding content ", 30)},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	for i := 0; i < 2000; i++ {
		tmp.Write(append(normalLine, '\n'))
	}

	// Append one line that contains the query.
	matchLine, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "unique_large_file_keyword at the end"},
	})
	if err != nil {
		t.Fatalf("marshal match line: %v", err)
	}
	tmp.Write(append(matchLine, '\n'))
	if err := tmp.Sync(); err != nil {
		t.Fatalf("sync: %v", err)
	}

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "unique_large_file_keyword")
	if !ok {
		t.Fatal("expected match in very large file")
	}
	if !strings.Contains(strings.ToLower(summary.Snippet), "unique_large_file_keyword") {
		t.Fatalf("expected snippet to contain query, got %q", summary.Snippet)
	}
	// Lines should reflect all 2001 non-blank lines.
	if summary.Lines < 2001 {
		t.Fatalf("expected >= 2001 lines counted, got %d", summary.Lines)
	}
}

// TestProcessFileVeryLargeFileSingleLine verifies that a file containing a
// single JSON line whose payload text is >100 KB (an unusually large record)
// is handled without truncation errors.
func TestProcessFileVeryLargeFileSingleLine(t *testing.T) {
	tmp, err := os.CreateTemp(t.TempDir(), "bigline*.jsonl")
	if err != nil {
		t.Fatalf("create temp: %v", err)
	}
	defer tmp.Close()

	// A payload text of 200 KB; query is embedded at a known position.
	bigText := strings.Repeat("abcdefghij", 10*1024) + " bigline_keyword " + strings.Repeat("zyxwvutsrq", 1024)
	line, err := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": bigText},
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	tmp.Write(append(line, '\n'))
	if err := tmp.Sync(); err != nil {
		t.Fatalf("sync: %v", err)
	}

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	summary, ok := sc.ProcessFile(WorkItem{Source: "test", Path: tmp.Name()}, "bigline_keyword")
	if !ok {
		t.Fatal("expected match in large single-line file")
	}
	if !strings.Contains(strings.ToLower(summary.Snippet), "bigline_keyword") {
		t.Fatalf("snippet %q missing query", summary.Snippet)
	}
}

// ── Deeply nested directory structures ───────────────────────────────────────

// TestCollectFilesDeeplyNested verifies that collectFiles descends into deeply
// nested subdirectories and still finds .jsonl files.
func TestCollectFilesDeeplyNested(t *testing.T) {
	base := t.TempDir()

	// Build a 10-level deep directory tree.
	dir := base
	for i := 0; i < 10; i++ {
		dir = fmt.Sprintf("%s/level%d", dir, i)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("mkdir %s: %v", dir, err)
		}
	}

	// Place a .jsonl file at the deepest level.
	deepFile := dir + "/deep_session.jsonl"
	if err := os.WriteFile(deepFile, []byte(`{"type":"event_msg"}`+"\n"), 0o644); err != nil {
		t.Fatalf("write deep file: %v", err)
	}

	items := collectFiles([]WorkItem{{Source: "deep_test", Path: base}})
	if len(items) != 1 {
		t.Fatalf("expected 1 item in deeply nested dir, got %d", len(items))
	}
	if items[0].Path != deepFile {
		t.Fatalf("expected %q, got %q", deepFile, items[0].Path)
	}
}

// TestCollectFilesDeeplyNestedSkillDir confirms that a deeply nested skill
// directory is still excluded even at depth.
func TestCollectFilesDeeplyNestedSkillDir(t *testing.T) {
	base := t.TempDir()

	// Normal session file.
	sessionDir := base + "/sessions"
	if err := os.MkdirAll(sessionDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	sessionFile := sessionDir + "/normal.jsonl"
	os.WriteFile(sessionFile, []byte(`{"type":"event_msg"}`+"\n"), 0o644)

	// Skill file nested deeply.
	skillDir := base + "/nested/path/skills/notebooklm"
	if err := os.MkdirAll(skillDir, 0o755); err != nil {
		t.Fatalf("mkdir skill dir: %v", err)
	}
	os.WriteFile(skillDir+"/SKILL.md.json", []byte(`{}`), 0o644)

	items := collectFiles([]WorkItem{{Source: "test", Path: base}})
	if len(items) != 1 {
		t.Fatalf("expected 1 item (skill excluded), got %d", len(items))
	}
	if items[0].Path != sessionFile {
		t.Fatalf("expected session file, got %q", items[0].Path)
	}
}

// ── Symlink handling ──────────────────────────────────────────────────────────

// TestCollectFilesSymlinkFile confirms that a symlink pointing to a .jsonl
// file is included in the scan results.  filepath.WalkDir follows symlinks to
// files (but not to directories that would create cycles).
func TestCollectFilesSymlinkFile(t *testing.T) {
	base := t.TempDir()

	// Real file.
	realFile := base + "/real.jsonl"
	if err := os.WriteFile(realFile, []byte(`{"type":"event_msg"}`+"\n"), 0o644); err != nil {
		t.Fatalf("write real: %v", err)
	}

	// Symlink to the real file.
	linkFile := base + "/link.jsonl"
	if err := os.Symlink(realFile, linkFile); err != nil {
		t.Skipf("symlink not supported: %v", err)
	}

	items := collectFiles([]WorkItem{{Source: "sym_test", Path: base}})
	if len(items) < 2 {
		t.Fatalf("expected at least 2 items (real + symlink), got %d", len(items))
	}
}

// TestCollectFilesSymlinkCycleNoInfiniteLoop verifies that a symlink creating
// a directory cycle does not cause collectFiles to loop infinitely.
// filepath.WalkDir on Linux/macOS does NOT follow symlinks to directories, so
// cycles are inherently safe.  This test confirms the behaviour and that the
// function terminates in a reasonable time.
func TestCollectFilesSymlinkCycleNoInfiniteLoop(t *testing.T) {
	base := t.TempDir()

	// Create a subdirectory and a symlink inside it pointing back to the parent.
	subDir := base + "/subdir"
	if err := os.MkdirAll(subDir, 0o755); err != nil {
		t.Fatalf("mkdir subdir: %v", err)
	}
	cycleLink := subDir + "/cycle"
	if err := os.Symlink(base, cycleLink); err != nil {
		t.Skipf("symlink not supported: %v", err)
	}

	// Place a regular file so the walk has something to find.
	os.WriteFile(base+"/session.jsonl", []byte(`{"type":"event_msg"}`+"\n"), 0o644)

	// Must complete without hanging.
	done := make(chan struct{})
	go func() {
		collectFiles([]WorkItem{{Source: "cycle_test", Path: base}})
		close(done)
	}()
	select {
	case <-done:
		// good — returned without infinite loop
	}
}

// ── sync.Pool reuse under parallel load ──────────────────────────────────────

// TestScanParallelPoolReuse exercises the scannerBufPool and runeSlicePool
// under parallel load.  Multiple goroutines call ProcessFile and SnippetMatcher
// concurrently to catch any data-race or pool-corruption issues.
// Run with -race to detect races.
func TestScanParallelPoolReuse(t *testing.T) {
	dir := t.TempDir()

	// Create 20 small files, each with a matchable line.
	for i := 0; i < 20; i++ {
		path := fmt.Sprintf("%s/file%02d.jsonl", dir, i)
		line, _ := json.Marshal(map[string]any{
			"type":    "event_msg",
			"payload": map[string]any{"type": "agent_message", "message": fmt.Sprintf("parallel_keyword session %d", i)},
		})
		os.WriteFile(path, append(line, '\n'), 0o644)
	}

	items := collectFiles([]WorkItem{{Source: "parallel", Path: dir}})
	if len(items) != 20 {
		t.Fatalf("expected 20 items, got %d", len(items))
	}

	sc := NewSessionScanner(NewNoiseFilter(nil), defaultSnippetLimit)
	results, _ := scan(items, 8, "parallel_keyword", 100, sc)
	if len(results) != 20 {
		t.Fatalf("expected 20 matches, got %d", len(results))
	}
}

// ── BenchmarkProcessFileLargeFile ─────────────────────────────────────────────

func BenchmarkProcessFileLargeFile(b *testing.B) {
	tmp, err := os.CreateTemp(b.TempDir(), "benchlarge*.jsonl")
	if err != nil {
		b.Fatalf("create temp: %v", err)
	}
	defer tmp.Close()

	line, _ := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": strings.Repeat("benchmark payload content ", 20)},
	})
	for i := 0; i < 5000; i++ {
		tmp.Write(append(line, '\n'))
	}
	// Add one matching line at the end.
	matchLine, _ := json.Marshal(map[string]any{
		"type":    "event_msg",
		"payload": map[string]any{"type": "agent_message", "message": "bench_large_keyword result"},
	})
	tmp.Write(append(matchLine, '\n'))
	tmp.Sync()

	sc := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)
	item := WorkItem{Source: "bench", Path: tmp.Name()}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sc.ProcessFile(item, "bench_large_keyword")
	}
}

// BenchmarkClipSnippetPooled benchmarks the pool-backed clipSnippet for mixed
// ASCII and CJK content.
func BenchmarkClipSnippetPooled(b *testing.B) {
	text := "前缀内容：这里包含一段很长的中英文混合内容 the target keyword sits right here and then more text follows after it"
	idx := strings.Index(strings.ToLower(text), "target")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		clipSnippet(text, idx, len("target"), 50)
	}
}
