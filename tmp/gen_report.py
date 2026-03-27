#!/usr/bin/env python3
"""Generate AutoResearch v0.9.2 HTML trend report."""
import json, base64, sys
from io import BytesIO

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib not available, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", "matplotlib"], stdout=subprocess.DEVNULL)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

UNIFIED_FONTS = ['PingFang SC', 'SimHei', 'Microsoft YaHei', 'DejaVu Sans', 'sans-serif']
plt.rcParams['font.family'] = ['sans-serif']
plt.rcParams['font.sans-serif'] = UNIFIED_FONTS
plt.rcParams['axes.unicode_minus'] = False

COLORS = {
    'keep': '#16a34a', 'discard': '#dc2626', 'crash': '#9333ea',
    'region_fail': '#f59e0b', 'line': '#2563eb', 'grid': '#e5e7eb'
}

rounds_data = [
    {"round": 0, "hypothesis": "Baseline", "total_score": 85.2, "decision": "KEEP",
     "dimension_scores": {"tests": 225, "coverage": 51.0, "lint": 90, "security": 80, "docs": 85},
     "notes": "Starting point"},
    {"round": 1, "hypothesis": "Test coverage expansion (core, native, server, noise_sync)", "total_score": 87.5, "decision": "KEEP",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 92, "security": 82, "docs": 85},
     "notes": "383 tests, 60.21% coverage"},
    {"round": 2, "hypothesis": "Region-restricted (API unavailable)", "total_score": 87.5, "decision": "CRASH",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 92, "security": 82, "docs": 85},
     "notes": "Region restriction"},
    {"round": 3, "hypothesis": "Rust clippy is_none_or fix", "total_score": 88.0, "decision": "KEEP",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 95, "security": 82, "docs": 85},
     "notes": "Native lint clean"},
    {"round": 4, "hypothesis": "Go zero-alloc rewrite", "total_score": 88.5, "decision": "KEEP",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 95, "security": 82, "docs": 87},
     "notes": "Scanner perf improved"},
    {"round": 5, "hypothesis": "Rust hot-path heap alloc elimination", "total_score": 89.0, "decision": "KEEP",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 95, "security": 82, "docs": 87},
     "notes": "9 functions optimized"},
    {"round": 6, "hypothesis": "Region-restricted x3", "total_score": 89.0, "decision": "CRASH",
     "dimension_scores": {"tests": 383, "coverage": 60.2, "lint": 95, "security": 82, "docs": 87},
     "notes": "Daemon already optimized"},
    {"round": 7, "hypothesis": "Daemon extended tests (80+ tests)", "total_score": 91.0, "decision": "KEEP",
     "dimension_scores": {"tests": 463, "coverage": 72.0, "lint": 95, "security": 82, "docs": 87},
     "notes": "Daemon coverage boost"},
    {"round": 8, "hypothesis": "Benchmark dedup + utility tests", "total_score": 91.5, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.9, "lint": 95, "security": 82, "docs": 87},
     "notes": "DRY benchmark code"},
    {"round": 9, "hypothesis": "Ruff version fix (0.9.10 -> 0.15.7 revert)", "total_score": 91.5, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.9, "lint": 95, "security": 82, "docs": 87},
     "notes": "CI alignment fix"},
    {"round": 10, "hypothesis": "CI actions version alignment", "total_score": 92.0, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.9, "lint": 96, "security": 82, "docs": 88},
     "notes": "checkout@v4, setup-python@v5"},
    {"round": 11, "hypothesis": "CORS origin bypass security fix", "total_score": 93.0, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 92, "docs": 88},
     "notes": "urlparse hostname validation"},
    {"round": 12, "hypothesis": "E2e quality gate expansion (export-import, maintain)", "total_score": 93.5, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 92, "docs": 89},
     "notes": "2 new e2e cases"},
    {"round": 13, "hypothesis": "Healthcheck diagnostic enhancement", "total_score": 93.8, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 92, "docs": 90},
     "notes": "Actionable error messages"},
    {"round": 14, "hypothesis": "Smoke runtime sandbox isolation", "total_score": 94.0, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 93, "docs": 90},
     "notes": "Temp dir sandbox"},
    {"round": 15, "hypothesis": "Token removal from docstring", "total_score": 94.2, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 94, "docs": 90},
     "notes": "context_server.py cleaned"},
    {"round": 16, "hypothesis": "Region-restricted (startup speed)", "total_score": 94.2, "decision": "CRASH",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 94, "docs": 90},
     "notes": "Region restriction"},
    {"round": 17, "hypothesis": "CLI error messages improvement", "total_score": 94.5, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 94, "docs": 91},
     "notes": "Actionable save/import errors"},
    {"round": 18, "hypothesis": "Type hints audit (already complete)", "total_score": 94.5, "decision": "KEEP",
     "dimension_scores": {"tests": 533, "coverage": 77.1, "lint": 96, "security": 94, "docs": 91},
     "notes": "All 3 core modules fully annotated"},
    {"round": 19, "hypothesis": "Go Unicode byte-offset bug fix", "total_score": 95.5, "decision": "KEEP",
     "dimension_scores": {"tests": 546, "coverage": 78.0, "lint": 97, "security": 94, "docs": 91},
     "notes": "clipRuneWindow extraction"},
    {"round": 20, "hypothesis": "Coverage push: 250 new tests (session_index, memory_index)", "total_score": 97.0, "decision": "KEEP",
     "dimension_scores": {"tests": 783, "coverage": 84.5, "lint": 97, "security": 94, "docs": 91},
     "notes": "memory_index 96%, session_index 90%"},
]

def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

# Chart 1: Score trend
fig, ax = plt.subplots(figsize=(14, 5))
rounds = [r['round'] for r in rounds_data]
scores = [r['total_score'] for r in rounds_data]
decisions = [r['decision'] for r in rounds_data]

ax.plot(rounds, scores, color=COLORS['line'], linewidth=2.5, marker='o', markersize=7, zorder=3)
for i, (r, s, d) in enumerate(zip(rounds, scores, decisions)):
    color = COLORS.get(d.lower(), '#666')
    ax.scatter([r], [s], color=color, s=100, zorder=5, edgecolors='white', linewidth=1)
    if i > 0:
        delta = s - scores[i-1]
        if abs(delta) > 0.01:
            ax.annotate(f'{delta:+.1f}', (r, s), textcoords="offset points",
                       xytext=(0, 14), ha='center', fontsize=7, color=color, fontweight='bold')

ax.set_xlabel('Round', fontsize=11)
ax.set_ylabel('Score', fontsize=11)
ax.set_title('ContextGO v0.9.2 AutoResearch Optimization Trend (20 Rounds)', fontsize=13, fontweight='bold')
ax.grid(True, alpha=0.3, color=COLORS['grid'])
ax.set_ylim(82, 100)
ax.set_xlim(-0.5, 20.5)
plt.tight_layout()
trend_img = fig_to_base64(fig)

# Chart 2: Coverage + Tests
fig, ax1 = plt.subplots(figsize=(14, 5))
tests = [r['dimension_scores']['tests'] for r in rounds_data]
coverage = [r['dimension_scores']['coverage'] for r in rounds_data]

color1 = '#3b82f6'
color2 = '#10b981'
ax1.bar(rounds, tests, color=color1, alpha=0.7, label='Tests', width=0.6)
ax1.set_xlabel('Round', fontsize=11)
ax1.set_ylabel('Test Count', color=color1, fontsize=11)
ax1.tick_params(axis='y', labelcolor=color1)

ax2 = ax1.twinx()
ax2.plot(rounds, coverage, color=color2, linewidth=2.5, marker='s', markersize=6, label='Coverage %')
ax2.set_ylabel('Coverage %', color=color2, fontsize=11)
ax2.tick_params(axis='y', labelcolor=color2)
ax2.set_ylim(45, 90)

fig.suptitle('Tests & Coverage Evolution', fontsize=13, fontweight='bold')
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
plt.tight_layout()
tests_img = fig_to_base64(fig)

# Chart 3: Decision distribution
from collections import Counter
dc = Counter(decisions)
labels_pie = list(dc.keys())
sizes = list(dc.values())
colors_pie = [COLORS.get(l.lower(), '#666') for l in labels_pie]
fig, ax = plt.subplots(figsize=(6, 6))
wedges, texts, autotexts = ax.pie(sizes, labels=labels_pie, colors=colors_pie, autopct='%1.0f%%',
                                   startangle=90, textprops={'fontsize': 11})
ax.set_title('Decision Distribution', fontsize=13, fontweight='bold')
plt.tight_layout()
pie_img = fig_to_base64(fig)

# Build HTML
stats = dict(dc)
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>ContextGO v0.9.2 AutoResearch Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #fff; color: #1a1a1a; }}
h1 {{ border-bottom: 3px solid #2563eb; padding-bottom: 10px; }}
h2 {{ color: #1e40af; margin-top: 30px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 6px 10px; text-align: center; }}
th {{ background: #f3f4f6; font-weight: bold; }}
.keep {{ color: #16a34a; font-weight: bold; }}
.crash {{ color: #9333ea; font-weight: bold; }}
.chart {{ text-align: center; margin: 20px 0; }}
.chart img {{ max-width: 100%; border: 1px solid #e5e7eb; border-radius: 4px; }}
.summary {{ background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 15px; margin: 15px 0; }}
.summary strong {{ color: #1e40af; }}
.grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; align-items: start; }}
</style>
</head>
<body>
<h1>ContextGO v0.9.2 -- AutoResearch Optimization Report</h1>

<div class="summary">
<strong>Total Rounds</strong>: 21 (R0-R20) |
<strong>Final Score</strong>: 97.0 |
<strong>Baseline</strong>: 85.2 |
<strong>Improvement</strong>: +11.8 |
<strong>Decisions</strong>: {' / '.join(f'{k}={v}' for k,v in stats.items())} |
<strong>Tests</strong>: 225 -> 783 |
<strong>Coverage</strong>: 51% -> 84.5%
</div>

<h2>1. Score Trend / Optimization Trend</h2>
<div class="chart"><img src="data:image/png;base64,{trend_img}" alt="Score Trend"></div>

<h2>2. Tests & Coverage Evolution</h2>
<div class="chart"><img src="data:image/png;base64,{tests_img}" alt="Tests and Coverage"></div>

<div class="grid">
<div>
<h2>3. Round Details</h2>
<table>
<tr><th>R</th><th>Hypothesis</th><th>Score</th><th>Delta</th><th>Decision</th><th>Notes</th></tr>
"""

for i, r in enumerate(rounds_data):
    delta = r['total_score'] - rounds_data[i-1]['total_score'] if i > 0 else 0
    css = r['decision'].lower()
    html += f'<tr><td>R{r["round"]:02d}</td><td style="text-align:left">{r["hypothesis"]}</td>'
    html += f'<td>{r["total_score"]:.1f}</td><td>{delta:+.1f}</td>'
    html += f'<td class="{css}">{r["decision"]}</td><td style="text-align:left">{r["notes"]}</td></tr>\n'

html += f"""</table>
</div>
<div>
<h2>4. Decisions</h2>
<div class="chart"><img src="data:image/png;base64,{pie_img}" alt="Decision Pie"></div>
</div>
</div>

<h2>5. Key Achievements</h2>
<ul>
<li><strong>Security</strong>: CORS origin bypass fix (memory_viewer hostname parsing)</li>
<li><strong>Stability</strong>: Go Unicode byte-offset bug fix, Go 1.19 compat</li>
<li><strong>Quality</strong>: 783 tests, 84.5% coverage, ruff/clippy/go-vet all clean</li>
<li><strong>DX</strong>: Actionable CLI error messages, sandbox smoke tests, enhanced diagnostics</li>
<li><strong>Zero new dependencies</strong>: All improvements within existing dep footprint</li>
</ul>

<p style="color:#6b7280;font-size:12px;margin-top:40px;">
Generated 2026-03-27 | ContextGO v0.9.2 | 20-round AutoResearch | Claude Opus 4.6
</p>
</body>
</html>"""

out_path = "/home/node/a0/workspace/a8fdfcdc-2bdb-421b-9574-2100be1ce464/workspace/outputs/contextgo_v092_autoresearch_report.html"
with open(out_path, 'w') as f:
    f.write(html)
print(f"Report written to {out_path}")
