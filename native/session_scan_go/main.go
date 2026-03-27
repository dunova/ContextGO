// Package main implements session_scan_go, a high-performance parallel scanner
// for AI coding session files (JSONL format). It discovers, filters, and indexes
// session content from Codex, Claude, and shell history sources.
//
// Usage:
//
//	session_scan_go [flags]
//
// See README.md for full documentation.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"text/tabwriter"
	"time"
)

// WorkItem pairs a file path with its logical source label.
type WorkItem struct {
	Source    string
	Path      string
	SizeBytes int64
}

// SessionSummary holds the metadata and best match extracted from one session
// file.  Fields tagged with omitempty are omitted from JSON when empty.
type SessionSummary struct {
	Source         string `json:"source"`
	Path           string `json:"path"`
	SessionID      string `json:"session_id"`
	Lines          int    `json:"lines"`
	SizeBytes      int64  `json:"size_bytes"`
	FirstTimestamp string `json:"first_timestamp,omitempty"`
	LastTimestamp  string `json:"last_timestamp,omitempty"`
	Snippet        string `json:"snippet,omitempty"`
	MatchField     string `json:"match_field,omitempty"`
	MatchScore     int    `json:"-"`
}

// ScanOutput is the top-level JSON envelope emitted when --json is set.
type ScanOutput struct {
	FilesScanned int              `json:"files_scanned"`
	Query        string           `json:"query,omitempty"`
	Matches      []SessionSummary `json:"matches"`
	Truncated    bool             `json:"truncated,omitempty"`
}

// Aggregates returns per-source statistics derived from the matched results.
func (o ScanOutput) Aggregates() []Aggregate {
	return summarize(o.Matches)
}

func main() {
	home, err := os.UserHomeDir()
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: cannot determine home directory: %v\n", err)
		home = "."
	}

	// Parse all flags up front; store in local vars to avoid repeated
	// pointer dereferences in the hot output path.
	codexRoot := flag.String("codex-root", filepath.Join(home, ".codex", "sessions"), "Root directory for Codex session files")
	claudeRoot := flag.String("claude-root", filepath.Join(home, ".claude", "projects"), "Root directory for Claude session files")
	threads := flag.Int("threads", 4, "Number of parallel worker goroutines")
	query := flag.String("query", "", "Return only results whose text contains this substring")
	limit := flag.Int("limit", 20, "Maximum number of results to return")
	jsonOutput := flag.Bool("json", false, "Emit machine-readable JSON instead of a human summary")
	batchOutput := flag.Bool("batch-output", false, "Write results as NDJSON (one JSON object per line) instead of a single JSON array; avoids buffering all results in memory. Implies --json output format.")
	flag.Parse()

	// Capture flag values once to avoid repeated pointer dereferences.
	codexRootVal := *codexRoot
	claudeRootVal := *claudeRoot
	threadsVal := *threads
	queryVal := *query
	limitVal := *limit
	jsonOutputVal := *jsonOutput
	batchOutputVal := *batchOutput

	start := time.Now()

	roots := []WorkItem{
		{Source: "codex_session", Path: codexRootVal},
		{Source: "codex_session", Path: filepath.Join(home, ".codex", "archived_sessions")},
		{Source: "claude_session", Path: claudeRootVal},
	}
	work := collectFiles(roots)

	scanner := NewSessionScanner(NewNoiseFilter(DefaultNoiseMarkers), defaultSnippetLimit)

	// --batch-output: stream NDJSON results directly to stdout without
	// accumulating all matches in memory.  Each result is emitted as a
	// separate JSON line the moment it is ready, making this mode suitable
	// for large result sets and downstream streaming consumers.
	if batchOutputVal {
		writeBatchOutput(work, threadsVal, queryVal, limitVal, scanner, start)
		return
	}

	results, truncated := scan(work, threadsVal, queryVal, limitVal, scanner)

	sort.Slice(results, func(i, j int) bool {
		a, b := results[i], results[j]
		if a.MatchScore != b.MatchScore {
			return a.MatchScore > b.MatchScore
		}
		if a.LastTimestamp != b.LastTimestamp {
			return a.LastTimestamp > b.LastTimestamp
		}
		if a.FirstTimestamp != b.FirstTimestamp {
			return a.FirstTimestamp > b.FirstTimestamp
		}
		if a.Source != b.Source {
			return a.Source < b.Source
		}
		return a.Path < b.Path
	})

	if limitVal > 0 && len(results) > limitVal {
		results = results[:limitVal]
		truncated = true
	}

	output := ScanOutput{
		FilesScanned: len(work),
		Query:        queryVal,
		Matches:      results,
		Truncated:    truncated,
	}

	if jsonOutputVal {
		raw, err := json.MarshalIndent(output, "", "  ")
		if err != nil {
			fmt.Fprintf(os.Stderr, "json marshal error: %v\n", err)
			os.Exit(1)
		}
		fmt.Println(string(raw))
		return
	}

	fmt.Printf("Scan complete: %d files, %d matches, elapsed %s.\n",
		len(work), len(results), time.Since(start).Round(time.Millisecond))

	aggs := output.Aggregates()
	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "source\tmatches\ttotal_lines\ttotal_bytes")
	for _, agg := range aggs {
		fmt.Fprintf(w, "%s\t%d\t%d\t%d\n", agg.Source, agg.Count, agg.TotalLines, agg.TotalSize)
	}
	if err := w.Flush(); err != nil {
		fmt.Fprintf(os.Stderr, "tabwriter flush: %v\n", err)
	}

	if truncated && limitVal > 0 {
		fmt.Printf("Results truncated at limit %d; additional matches may exist.\n", limitVal)
	}
}

// writeBatchOutput streams scan results as NDJSON to stdout.  Each
// SessionSummary is written as one JSON line immediately when produced,
// without accumulating the full result set in memory.  A final metadata
// line is appended after all results.
func writeBatchOutput(work []WorkItem, threads int, query string, limit int, scanner *SessionScanner, start time.Time) {
	if threads < 1 {
		threads = 1
	}

	workCh := make(chan WorkItem, threads*2)
	resultCh := make(chan SessionSummary, threads*2)

	var wg sync.WaitGroup
	for i := 0; i < threads; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range workCh {
				if summary, ok := scanner.ProcessFile(item, query); ok {
					resultCh <- summary
				}
			}
		}()
	}

	go func() {
		for _, item := range work {
			workCh <- item
		}
		close(workCh)
		wg.Wait()
		close(resultCh)
	}()

	bw := bufio.NewWriterSize(os.Stdout, 64*1024)
	enc := json.NewEncoder(bw)
	enc.SetEscapeHTML(false)

	count := 0
	truncated := false
	for result := range resultCh {
		if limit > 0 && count >= limit {
			truncated = true
			// Drain remaining results to avoid blocking workers.
			continue
		}
		if err := enc.Encode(result); err != nil {
			fmt.Fprintf(os.Stderr, "json encode error: %v\n", err)
		}
		count++
	}

	// Emit a trailing metadata line so consumers can detect end-of-stream.
	meta := struct {
		FilesScanned int    `json:"files_scanned"`
		Query        string `json:"query,omitempty"`
		Truncated    bool   `json:"truncated,omitempty"`
		ElapsedMs    int64  `json:"elapsed_ms"`
	}{
		FilesScanned: len(work),
		Query:        query,
		Truncated:    truncated,
		ElapsedMs:    time.Since(start).Milliseconds(),
	}
	if err := enc.Encode(meta); err != nil {
		fmt.Fprintf(os.Stderr, "json encode meta error: %v\n", err)
	}

	if err := bw.Flush(); err != nil {
		fmt.Fprintf(os.Stderr, "flush error: %v\n", err)
	}
}

// collectFiles walks each root directory and returns WorkItems for all .json
// and .jsonl files, skipping skill directories.
// filepath.WalkDir is used in preference to filepath.Walk because it passes
// a lightweight os.DirEntry instead of a fully-populated os.FileInfo, avoiding
// a stat(2) syscall per entry on most platforms.
func collectFiles(roots []WorkItem) []WorkItem {
	items := make([]WorkItem, 0, 64)
	for _, root := range roots {
		if _, err := os.Stat(root.Path); err != nil {
			continue
		}
		walkErr := filepath.WalkDir(root.Path, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: skipping %s: %v\n", path, err)
				return nil
			}
			if d == nil || d.IsDir() {
				return nil
			}
			if shouldSkipPath(path) {
				return nil
			}
			switch filepath.Ext(path) {
			case ".jsonl", ".json":
				items = append(items, WorkItem{Source: root.Source, Path: path})
			}
			return nil
		})
		if walkErr != nil {
			fmt.Fprintf(os.Stderr, "walk error for %s: %v\n", root.Path, walkErr)
		}
	}
	return items
}

// shouldSkipPath reports whether path belongs to a skill directory that should
// be excluded from session scanning.
func shouldSkipPath(path string) bool {
	lower := strings.ToLower(path)
	return strings.Contains(lower, "/skills/") || strings.Contains(lower, "skills-repo")
}

// scan fans out WorkItems to threads workers, collects SessionSummary results,
// and returns them together with a truncated flag (always false here; the
// caller applies the limit after sorting).
func scan(items []WorkItem, threads int, query string, limit int, scanner *SessionScanner) ([]SessionSummary, bool) {
	if threads < 1 {
		threads = 1
	}

	workCh := make(chan WorkItem, threads*2)
	resultCh := make(chan SessionSummary, threads*2)

	var wg sync.WaitGroup
	for i := 0; i < threads; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range workCh {
				if summary, ok := scanner.ProcessFile(item, query); ok {
					resultCh <- summary
				}
			}
		}()
	}

	go func() {
		for _, item := range items {
			workCh <- item
		}
		close(workCh)
		wg.Wait()
		close(resultCh)
	}()

	initialCap := len(items)
	if limit*2 < initialCap {
		initialCap = limit * 2
	}
	if initialCap < 16 {
		initialCap = 16
	}
	results := make([]SessionSummary, 0, initialCap)
	for result := range resultCh {
		results = append(results, result)
	}
	return results, false
}
