# 基准测试脚手架

本目录提供一个可重复执行的 Python 基准套件，用来衡量主链核心路径的性能：

- `context_cli.py health`（包含 session index 同步）
- `context_cli.py search`（精确查找）
- `session_index.sync_session_index`（强制重建本地索引）

### 用法

```
python -m benchmarks.run [--mode python|native] [--format text|json]
# 或
python -m benchmarks [--mode python|native] [--format text|json]
```

可选参数：`--iterations`、`--warmup`、`--query`、`--search-limit`，均支持环境变量 `CMF_BENCH_*` 覆盖（如 `CMF_BENCH_QUERY`、`CMF_BENCH_ITERATIONS`、`CMF_BENCH_SEARCH_LIMIT`）。脚本会在一次临时的 `HOME` 环境下生成样本 `.codex`、`.claude`、`.zsh_history` 等数据，避免依赖实际用户目录。

### 比较 Python/Native 路径

```
python -m benchmarks --mode python --format json > python.json
python -m benchmarks --mode native --format json > native.json
diff python.json native.json
```

为了向后兼容，`python benchmarks/session_index_benchmark.py` 仍然可用，它只是调用了 `--mode native --format json` 的统一入口。
