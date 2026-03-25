package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type WorkItem struct {
	Source string
	Path   string
}

type SessionSummary struct {
	Source    string `json:"source"`
	Path      string `json:"path"`
	SessionID string `json:"session_id"`
	Lines     int    `json:"lines"`
	SizeBytes int64  `json:"size_bytes"`
	Snippet    string `json:"snippet,omitempty"`
}

type ScanOutput struct {
	FilesScanned int              `json:"files_scanned"`
	Query        string           `json:"query,omitempty"`
	Matches      []SessionSummary `json:"matches"`
}

func main() {
	codexRoot := flag.String("codex-root", filepath.Join(os.Getenv("HOME"), ".codex", "sessions"), "Codex 会话根目录")
	claudeRoot := flag.String("claude-root", filepath.Join(os.Getenv("HOME"), ".claude", "projects"), "Claude 会话根目录")
	threads := flag.Int("threads", 4, "并发 worker 数")
	query := flag.String("query", "", "仅保留包含 query 的结果")
	jsonOutput := flag.Bool("json", false, "输出 JSON")
	flag.Parse()

	start := time.Now()
	work := collectFiles([]WorkItem{
		{Source: "codex_session", Path: *codexRoot},
		{Source: "claude_session", Path: *claudeRoot},
	})

	results := scan(work, *threads, *query)
	if *jsonOutput {
		payload := ScanOutput{
			FilesScanned: len(work),
			Query:        *query,
			Matches:      results,
		}
		raw, _ := json.MarshalIndent(payload, "", "  ")
		fmt.Println(string(raw))
		return
	}
	fmt.Printf("扫描完毕：%d 文件，耗时 %s。\n", len(results), time.Since(start).Round(time.Millisecond))
	for _, item := range summarize(results) {
		fmt.Printf("%s -> %d 文件, 总行数 %d, 总体积 %d 字节\n", item.Source, item.Count, item.TotalLines, item.TotalSize)
	}
}

func collectFiles(roots []WorkItem) []WorkItem {
	items := make([]WorkItem, 0)
	for _, root := range roots {
		if _, err := os.Stat(root.Path); err != nil {
			continue
		}
		_ = filepath.Walk(root.Path, func(path string, info os.FileInfo, err error) error {
			if err != nil || info == nil || info.IsDir() {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(path))
			if ext == ".jsonl" || ext == ".json" {
				items = append(items, WorkItem{Source: root.Source, Path: path})
			}
			return nil
		})
	}
	return items
}

func scan(items []WorkItem, threads int, query string) []SessionSummary {
	if threads < 1 {
		threads = 1
	}
	workCh := make(chan WorkItem)
	resultCh := make(chan SessionSummary)
	var wg sync.WaitGroup
	for range threads {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range workCh {
				if summary, ok := processFile(item, query); ok {
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

	results := make([]SessionSummary, 0, len(items))
	for result := range resultCh {
		results = append(results, result)
	}
	return results
}

func processFile(item WorkItem, query string) (SessionSummary, bool) {
	file, err := os.Open(item.Path)
	if err != nil {
		return SessionSummary{}, false
	}
	defer file.Close()
	stat, err := file.Stat()
	if err != nil {
		return SessionSummary{}, false
	}

	summary := SessionSummary{
		Source:    item.Source,
		Path:      item.Path,
		SessionID: strings.TrimSuffix(filepath.Base(item.Path), filepath.Ext(item.Path)),
		SizeBytes: stat.Size(),
	}
	queryLower := strings.ToLower(strings.TrimSpace(query))
	matchFound := queryLower == ""

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		summary.Lines++
		if queryLower != "" && strings.Contains(strings.ToLower(line), queryLower) && summary.Snippet == "" {
			matchFound = true
			if len(line) > 220 {
				summary.Snippet = line[:220]
			} else {
				summary.Snippet = line
			}
		}
		var payload map[string]any
		if err := json.Unmarshal([]byte(line), &payload); err == nil {
			if sid := extractSessionID(payload); sid != "" {
				summary.SessionID = sid
			}
		}
	}
	return summary, matchFound
}

func extractSessionID(payload map[string]any) string {
	if sessionID, ok := payload["sessionId"].(string); ok && sessionID != "" {
		return sessionID
	}
	if nested, ok := payload["payload"].(map[string]any); ok {
		if id, ok := nested["id"].(string); ok && id != "" {
			return id
		}
	}
	return ""
}

type Aggregate struct {
	Source     string
	Count      int
	TotalLines int
	TotalSize  int64
}

func summarize(results []SessionSummary) []Aggregate {
	m := map[string]*Aggregate{}
	for _, result := range results {
		agg, ok := m[result.Source]
		if !ok {
			agg = &Aggregate{Source: result.Source}
			m[result.Source] = agg
		}
		agg.Count++
		agg.TotalLines += result.Lines
		agg.TotalSize += result.SizeBytes
	}
	out := make([]Aggregate, 0, len(m))
	for _, agg := range m {
		out = append(out, *agg)
	}
	return out
}
