package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// makeTempJSONL writes n JSONL lines to a temporary file and returns its path.
// The caller is responsible for removing the file.
func makeTempJSONL(tb testing.TB, lines int) string {
	tb.Helper()
	f, err := os.CreateTemp("", "bench_scan_*.jsonl")
	if err != nil {
		tb.Fatalf("CreateTemp: %v", err)
	}
	defer f.Close()

	for i := 0; i < lines; i++ {
		record := map[string]any{
			"type":      "event_msg",
			"sessionId": fmt.Sprintf("sess-%04d", i),
			"createdAt": "2025-01-01T00:00:00Z",
			"message":   fmt.Sprintf("This is test message number %d about memory optimization", i),
			"payload": map[string]any{
				"type":      "user_message",
				"text":      fmt.Sprintf("User asked about memory and performance at step %d", i),
				"timestamp": "2025-01-01T00:00:00Z",
			},
		}
		b, _ := json.Marshal(record)
		b = append(b, '\n')
		if _, err := f.Write(b); err != nil {
			tb.Fatalf("write: %v", err)
		}
	}
	return f.Name()
}

// makeTempLargeJSONL creates a file > mmapThreshold (1 MB) for mmap benchmarks.
func makeTempLargeJSONL(tb testing.TB) string {
	tb.Helper()
	// Each record is ~200 bytes; 6000 lines ≈ 1.2 MB.
	return makeTempJSONL(tb, 6000)
}

// ── BenchmarkScanFile ─────────────────────────────────────────────────────────

// BenchmarkScanFile measures end-to-end throughput of ProcessFile on a small
// JSONL file (< mmapThreshold) using the pooled bufio.Scanner path.
func BenchmarkScanFile(b *testing.B) {
	path := makeTempJSONL(b, 200)
	defer os.Remove(path)

	filter := NewNoiseFilter(DefaultNoiseMarkers)
	s := NewSessionScanner(filter, defaultSnippetLimit)
	item := WorkItem{Source: "bench", Path: path}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_, _ = s.ProcessFile(item, "memory")
	}
}

// BenchmarkScanFileLarge measures ProcessFile on a file > mmapThreshold,
// exercising the memory-mapped I/O path on Linux (falls back to buffered
// reading on other platforms where mmap is not available).
func BenchmarkScanFileLarge(b *testing.B) {
	path := makeTempLargeJSONL(b)
	defer os.Remove(path)

	fi, err := os.Stat(path)
	if err != nil {
		b.Fatalf("stat: %v", err)
	}
	b.Logf("large file size: %d bytes", fi.Size())

	filter := NewNoiseFilter(DefaultNoiseMarkers)
	s := NewSessionScanner(filter, defaultSnippetLimit)
	item := WorkItem{Source: "bench", Path: path}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_, _ = s.ProcessFile(item, "memory")
	}
}

// BenchmarkScanFileNoQuery measures ProcessFile with an empty query (list-all
// mode) to isolate I/O and JSON-parsing cost from search matching.
func BenchmarkScanFileNoQuery(b *testing.B) {
	path := makeTempJSONL(b, 200)
	defer os.Remove(path)

	filter := NewNoiseFilter(DefaultNoiseMarkers)
	s := NewSessionScanner(filter, defaultSnippetLimit)
	item := WorkItem{Source: "bench", Path: path}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_, _ = s.ProcessFile(item, "")
	}
}

// ── BenchmarkContainsFold ─────────────────────────────────────────────────────

// BenchmarkContainsFold measures containsFoldASCII on a realistic session line.
func BenchmarkContainsFold(b *testing.B) {
	haystack := []byte(`{"type":"event_msg","message":"User asked about memory optimization and performance tuning in Go"}`)
	needle := []byte("memory")

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = containsFoldASCII(haystack, needle)
	}
}

// BenchmarkContainsFoldMiss measures containsFoldASCII when the needle is
// absent (worst-case linear scan).
func BenchmarkContainsFoldMiss(b *testing.B) {
	haystack := []byte(`{"type":"event_msg","message":"This line does not contain the search term at all, it is entirely unrelated content for the benchmark"}`)
	needle := []byte("xyzzy")

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = containsFoldASCII(haystack, needle)
	}
}

// BenchmarkContainsFoldMixedCase benchmarks case-insensitive matching when
// haystack contains mixed-case occurrences of the needle.
func BenchmarkContainsFoldMixedCase(b *testing.B) {
	haystack := []byte(`{"type":"event_msg","message":"MEMORY optimization improved MEMORY usage and memory allocation patterns"}`)
	needle := []byte("memory")

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = containsFoldASCII(haystack, needle)
	}
}

// ── BenchmarkParseJSONL ───────────────────────────────────────────────────────

// BenchmarkParseJSONL measures the cost of JSON unmarshalling a typical
// session record into a map[string]any, reflecting the hot path inside
// ProcessFile.
func BenchmarkParseJSONL(b *testing.B) {
	line := []byte(`{"type":"event_msg","sessionId":"abc-123","createdAt":"2025-01-01T00:00:00Z","message":"Working on memory optimization for Go scanner","payload":{"type":"user_message","text":"Optimize bufio.Scanner pooling and mmap support","timestamp":"2025-01-01T00:00:00Z","cwd":"/home/user/project"}}`)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		var payload map[string]any
		_ = json.Unmarshal(line, &payload)
	}
}

// BenchmarkParseJSONLExtract measures JSON parse + field extraction together.
func BenchmarkParseJSONLExtract(b *testing.B) {
	line := []byte(`{"type":"event_msg","sessionId":"abc-123","createdAt":"2025-01-01T00:00:00Z","message":"Working on memory optimization for Go scanner","payload":{"type":"user_message","text":"Optimize bufio.Scanner pooling and mmap support","timestamp":"2025-01-01T00:00:00Z","cwd":"/home/user/project"}}`)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		var payload map[string]any
		if err := json.Unmarshal(line, &payload); err == nil {
			_ = extractTextCandidates(payload)
			_ = extractTimestamp(payload)
			_ = extractSessionID(payload)
			_ = extractCwd(payload)
		}
	}
}

// BenchmarkParseJSONLStream simulates incremental JSONL streaming by
// processing a slice of pre-serialised lines as ProcessFile does internally.
func BenchmarkParseJSONLStream(b *testing.B) {
	records := make([][]byte, 100)
	for i := range records {
		rec := map[string]any{
			"type":      "event_msg",
			"sessionId": fmt.Sprintf("sess-%04d", i),
			"createdAt": "2025-01-01T00:00:00Z",
			"message":   fmt.Sprintf("Benchmark record %d about session memory optimization", i),
			"payload": map[string]any{
				"type":      "user_message",
				"text":      fmt.Sprintf("Detail %d", i),
				"timestamp": "2025-01-01T00:00:00Z",
			},
		}
		records[i], _ = json.Marshal(rec)
	}
	query := []byte("memory")

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		for _, line := range records {
			if containsFoldASCII(line, query) {
				var payload map[string]any
				if err := json.Unmarshal(line, &payload); err == nil {
					_ = extractTextCandidates(payload)
				}
			}
		}
	}
}

// ── BenchmarkProcessLines ─────────────────────────────────────────────────────

// BenchmarkProcessLines measures the processLines function on a byte buffer
// that mimics a memory-mapped JSONL file.
func BenchmarkProcessLines(b *testing.B) {
	var sb strings.Builder
	for i := 0; i < 500; i++ {
		rec := map[string]any{
			"type":    "event_msg",
			"message": fmt.Sprintf("Line %d: memory optimization benchmark data", i),
		}
		data, _ := json.Marshal(rec)
		sb.Write(data)
		sb.WriteByte('\n')
	}
	raw := []byte(sb.String())
	noop := func(_ []byte) {}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		buf := raw // avoid mutation aliasing
		processLines(buf, noop)
	}
}

// ── BenchmarkNoiseFilter ──────────────────────────────────────────────────────

// BenchmarkNoiseFilterClean measures IsNoiseLower on a line that passes all
// filters (the common case for real content).
func BenchmarkNoiseFilterClean(b *testing.B) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	line := "the user asked for a detailed explanation of memory management in go"

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = filter.IsNoiseLower(line)
	}
}

// BenchmarkNoiseFilterNoisy measures IsNoiseLower on a line that matches a
// noise marker early in the list.
func BenchmarkNoiseFilterNoisy(b *testing.B) {
	filter := NewNoiseFilter(DefaultNoiseMarkers)
	line := "## heading style line that matches the prefix filter immediately"

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = filter.IsNoiseLower(line)
	}
}
