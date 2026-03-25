# Native Prototypes

这里放渐进式高性能重写原型，而不是一次性推倒重来。

当前原型：

- `session_scan/`
  Rust 版并行会话扫描器，用于验证高性能 JSONL 扫描路径。
- `session_scan_go/`
  Go 版最小会话扫描器，用于验证轻量单二进制路线。

构建运行：

```bash
cd native/session_scan
CARGO_TARGET_DIR=/tmp/context_mesh_target cargo run --release -- --threads 4

cd native/session_scan_go
go run . --threads 4
```

定位：

- 先验证热点是否值得重写
- 先重写 `session_index` / 会话扫描热路径
- Python 继续保留 CLI、部署、兼容层
