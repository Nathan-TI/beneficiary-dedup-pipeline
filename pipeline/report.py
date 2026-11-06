"""Self-contained HTML report (no external assets) — works offline and on GitHub Pages."""
from __future__ import annotations

import html
from datetime import date

import pandas as pd

from .dedup import MATCH_AT, REVIEW_AT

E = html.escape


def _fmt(n) -> str:
    return f"{n:,}"


def _kpis(s: dict) -> str:
    pct_blocked = 100 * (1 - s["candidate_pairs"] / s["all_possible_pairs"])
    m = (s.get("metrics") or {}).get("pipeline")
    tiles = [
        ("Records in", _fmt(s["records_in"]), "raw registrations"),
        ("Unique people", _fmt(s["people_out"]), f"{_fmt(s['duplicates_removed'])} duplicates merged"),
        ("Comparisons skipped", f"{pct_blocked:.2f}%", f"{_fmt(s['candidate_pairs'])} of {_fmt(s['all_possible_pairs'])} pairs scored"),
        ("Records with DQ issues", _fmt(s["records_with_issues"]),
         f"{100 * s['records_with_issues'] / s['records_in']:.1f}% of records"),
    ]
    if m:
        tiles.insert(2, ("Duplicate pairs found", f"{100 * m['recall']:.1f}%",
                         f"precision {100 * m['precision']:.1f}% · {m['fp']} false merges"))
    return "".join(
        f'<div class="tile"><div class="t-label">{a}</div><div class="t-value">{b}</div>'
        f'<div class="t-sub">{c}</div></div>' for a, b, c in tiles)


def _accuracy_chart(metrics: dict) -> str:
    series = [("baseline", "Exact name + DOB match", "var(--series-1)"),
              ("pipeline", "This pipeline (auto)", "var(--series-2)"),
              ("pipeline_after_review", "After review queue", "var(--series-3)")]
    groups = [("precision", "Precision"), ("recall", "Recall"), ("f1", "F1 score")]
    W, left, right, bar, gap, ggap = 640, 92, 56, 16, 2, 22
    plot_w = W - left - right
    y, parts = 8, []
    for gi, (key, label) in enumerate(groups):
        gh = len(series) * bar + (len(series) - 1) * gap
        parts.append(f'<text x="{left - 12}" y="{y + gh / 2 + 4}" text-anchor="end" class="ax">{label}</text>')
        for si, (sk, sname, col) in enumerate(series):
            v = metrics[sk][key]
            w = max(2, plot_w * v)
            by = y + si * (bar + gap)
            parts.append(
                f'<g class="hit" data-tip="{E(sname)} · {label}: {100 * v:.1f}%">'
                f'<rect x="{left}" y="{by - 1}" width="{plot_w}" height="{bar + 2}" fill="transparent"/>'
                f'<path d="M{left},{by} h{w - 4} a4,4 0 0 1 4,4 v{bar - 8} a4,4 0 0 1 -4,4 h-{w - 4} z" fill="{col}"/>'
                f'<text x="{left + w + 6}" y="{by + bar - 4}" class="val">{100 * v:.1f}%</text></g>')
        y += gh + ggap
    for t in (0, 0.5, 1):
        x = left + plot_w * t
        parts.insert(0, f'<line x1="{x}" x2="{x}" y1="0" y2="{y - ggap + 8}" class="grid"/>'
                        f'<text x="{x}" y="{y - ggap + 24}" text-anchor="middle" class="ax">{int(t * 100)}%</text>')
    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{E(n)}</span>' for _, n, c in series)
    return (f'<div class="legend">{legend}</div>'
            f'<svg viewBox="0 0 {W} {y - ggap + 30}" role="img" aria-label="Precision, recall and F1 by method">'
            f'{"".join(parts)}</svg>')


def _hbar(rows: list[tuple[str, float, str]], unit: str = "", label_w: int = 230, aria: str = "") -> str:
    W, right, bar, gap = 640, 70, 16, 8
    plot_w = W - label_w - right
    mx = max(v for _, v, _ in rows) or 1
    parts, y = [], 4
    for label, v, tip in rows:
        w = max(2, plot_w * v / mx)
        txt = f"{v:,.1f}{unit}" if unit else _fmt(int(v))
        parts.append(
            f'<g class="hit" data-tip="{E(tip)}">'
            f'<rect x="0" y="{y - 3}" width="{W}" height="{bar + 6}" fill="transparent"/>'
            f'<text x="{label_w - 12}" y="{y + bar - 4}" text-anchor="end" class="ax">{E(label)}</text>'
            f'<path d="M{label_w},{y} h{w - 4} a4,4 0 0 1 4,4 v{bar - 8} a4,4 0 0 1 -4,4 h-{w - 4} z" fill="var(--series-1)"/>'
            f'<text x="{label_w + w + 6}" y="{y + bar - 4}" class="val">{txt}</text></g>')
        y += bar + gap
    return f'<svg viewBox="0 0 {W} {y}" role="img" aria-label="{E(aria)}">{"".join(parts)}</svg>'


def _score_hist(scored: pd.DataFrame) -> str:
    W, H, left, bottom, top = 640, 236, 44, 30, 38
    bins = [i / 40 for i in range(41)]
    counts = pd.cut(scored["score"], bins, include_lowest=True).value_counts(sort=False).tolist()
    mx = max(counts)
    plot_w, plot_h = W - left - 10, H - bottom - top
    bw = plot_w / 40
    parts = []
    for t in (0, mx // 2, mx):
        yy = top + plot_h * (1 - t / mx)
        parts.append(f'<line x1="{left}" x2="{W - 10}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{_fmt(t)}</text>')
    for i, c in enumerate(counts):
        h = plot_h * c / mx
        x = left + i * bw
        lo, hi = bins[i], bins[i + 1]
        parts.append(
            f'<g class="hit" data-tip="Score {lo:.3f}–{hi:.3f}: {_fmt(c)} pairs">'
            f'<rect x="{x}" y="{top}" width="{bw}" height="{plot_h}" fill="transparent"/>'
            + (f'<path d="M{x + 1},{top + plot_h} v-{max(h - 3, 0)} a3,3 0 0 1 3,-3 h{bw - 8} a3,3 0 0 1 3,3 v{max(h - 3, 0)} z" fill="var(--series-1)"/>' if c else "")
            + "</g>")
    for thr, lab, ty in ((REVIEW_AT, f"review ≥ {REVIEW_AT}", top - 6),
                         (MATCH_AT, f"auto-merge ≥ {MATCH_AT}", top - 22)):
        x = left + plot_w * thr
        parts.append(f'<line x1="{x}" x2="{x}" y1="{ty - 4}" y2="{top + plot_h}" class="thr"/>'
                     f'<text x="{x - 5}" y="{ty}" text-anchor="end" class="ax">{lab}</text>')
    for t in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<text x="{left + plot_w * t}" y="{H - 10}" text-anchor="middle" class="ax">{t:.2f}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Distribution of candidate pair scores">{"".join(parts)}</svg>'


def _table(df: pd.DataFrame, cls: str = "") -> str:
    head = "".join(f"<th>{E(str(c))}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{'' if pd.isna(v) else E(str(v))}</td>" for v in row) + "</tr>"
                   for row in df.itertuples(index=False))
    return f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _example_clusters(gold: pd.DataFrame, raw: pd.DataFrame, k: int = 5) -> str:
    multi = gold[gold["n_records"] > 1]
    cols = ["record_id", "first_name", "father_name", "grandfather_name", "sex", "date_of_birth", "phone", "kebele"]
    picked = []
    for _, g in multi.iterrows():
        ids = g["merged_record_ids"].split(";")
        sub = raw[raw["record_id"].isin(ids)]
        if sub["first_name"].astype(str).str.strip().str.lower().nunique() > 1 or \
           sub["date_of_birth"].nunique() > 1:
            picked.append(sub[cols])
        if len(picked) == k:
            break
    blocks = []
    for i, sub in enumerate(picked, 1):
        blocks.append(f'<h4>Person {i} — {len(sub)} registrations merged</h4>' + _table(sub, "small"))
    return "".join(blocks)


CSS = """
.viz-root{color-scheme:light;--surface-0:#f4f3ef;--surface-1:#fcfcfb;--text-primary:#0b0b0b;--text-secondary:#52514e;
--text-muted:#7a7974;--rule:#e2e1dc;--series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#121211;
--surface-1:#1a1a19;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--rule:#2e2e2b;
--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;}}
*{box-sizing:border-box}body{margin:0}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100vh}
.wrap{max-width:980px;margin:0 auto;padding:40px 20px 64px}
header h1{font-size:30px;line-height:1.2;margin:0 0 8px;letter-spacing:-.01em}
header p{color:var(--text-secondary);margin:0;max-width:720px}
.meta{font-size:13px;color:var(--text-muted);margin-top:10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:28px 0}
.tile{background:var(--surface-1);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.t-label{font-size:12px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}
.t-value{font-size:28px;font-weight:600;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.t-sub{font-size:12.5px;color:var(--text-muted)}
section{background:var(--surface-1);border:1px solid var(--rule);border-radius:12px;padding:22px 22px 18px;margin:16px 0}
section h2{font-size:18px;margin:0 0 4px}section .lede{color:var(--text-secondary);margin:0 0 14px;font-size:14px}
h4{font-size:14px;margin:18px 0 6px;color:var(--text-secondary);font-weight:600}
svg{width:100%;height:auto;display:block;overflow:visible}
svg text{font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.ax{fill:var(--text-secondary)}.val{fill:var(--text-primary);font-variant-numeric:tabular-nums}
.grid{stroke:var(--rule);stroke-width:1}.thr{stroke:var(--text-secondary);stroke-width:1.5;stroke-dasharray:4 3}
.hit{cursor:default}.hit:hover path{opacity:.8}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--text-secondary);margin-bottom:10px}
.lg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.tbl-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--text-secondary);font-weight:600;border-bottom:1px solid var(--rule);padding:6px 8px;white-space:nowrap}
td{border-bottom:1px solid var(--rule);padding:6px 8px;white-space:nowrap}table.small td,table.small th{padding:4px 8px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;counter-reset:s}@media(max-width:760px){.steps{grid-template-columns:1fr 1fr}}@media(max-width:440px){.steps{grid-template-columns:1fr}}
.step{border:1px solid var(--rule);border-radius:10px;padding:12px;font-size:13.5px;color:var(--text-secondary)}
.step b{display:block;color:var(--text-primary);font-size:14px;margin-bottom:4px}
.step b::before{counter-increment:s;content:counter(s) ". ";color:var(--text-muted)}
#tip{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);font-size:12.5px;padding:6px 9px;
border-radius:6px;opacity:0;transition:opacity .08s;z-index:10;max-width:280px}
footer{color:var(--text-muted);font-size:13px;margin-top:28px}
"""

JS = """
const tip=document.getElementById('tip');
document.querySelectorAll('.hit').forEach(g=>{
  g.addEventListener('mousemove',e=>{tip.textContent=g.dataset.tip;tip.style.opacity=1;
    const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px';});
  g.addEventListener('mouseleave',()=>tip.style.opacity=0);
});
"""


def build(summary: dict, issues: pd.DataFrame, comp: pd.DataFrame, scored: pd.DataFrame,
          gold: pd.DataFrame, raw: pd.DataFrame) -> str:
    metrics = summary.get("metrics")
    by_rule = (issues.groupby(["rule", "severity"]).size().reset_index(name="n")
               .sort_values("n", ascending=False))
    rule_rows = [(f"{r.rule} ({r.severity})", r.n, f"{r.rule} — {r.severity}: {r.n:,} records")
                 for r in by_rule.itertuples()]
    comp_rows = [(r.field.replace("_", " "), float(r.filled_pct), f"{r.field}: {r.filled_pct}% filled")
                 for r in comp.sort_values("filled_pct").itertuples()]

    review = scored[scored["decision"] == "review"].head(10).copy()
    review = review[["left", "right", "score", "sim_first", "sim_father", "sim_grandfather", "sim_dob", "sim_phone", "sim_location"]]
    review.columns = ["Record A", "Record B", "Score", "First", "Father", "Grandfather", "DOB", "Phone", "Location"]

    accuracy = ""
    if metrics:
        b, p, r = metrics["baseline"], metrics["pipeline"], metrics["pipeline_after_review"]
        accuracy = f"""
<section><h2>Accuracy against ground truth</h2>
<p class="lede">Because the data is synthetic, every true duplicate is known, so accuracy can be measured rather than guessed.
Exact matching finds only {100 * b['recall']:.0f}% of duplicate pairs. Fuzzy matching with domain rules finds
{100 * p['recall']:.1f}% automatically with {p['fp']} false merges, and {100 * r['recall']:.1f}% once the review queue is worked.</p>
{_accuracy_chart(metrics)}</section>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beneficiary Deduplication &amp; Data-Quality Pipeline — Report</title><style>{CSS}</style></head>
<body><div class="viz-root"><div class="wrap">
<header><h1>Beneficiary Deduplication &amp; Data-Quality Pipeline</h1>
<p>An end-to-end pipeline that checks registration data for quality problems, then finds people registered more than once,
even when names are spelled differently, dates of birth are mistyped, or phone numbers are written in different formats.</p>
<div class="meta">All data is synthetic, and no real person is represented · Run {date.today().isoformat()} · {summary['runtime_s']}s runtime</div></header>
<div class="tiles">{_kpis(summary)}</div>
<section><h2>How it works</h2><p class="lede">The same steps a registration team follows before a distribution list goes out.</p>
<div class="steps">
<div class="step"><b>Generate</b>Synthetic registrations with planted duplicates, sibling look-alikes and typical field errors.</div>
<div class="step"><b>Check quality</b>{len(by_rule)} rules for missing, invalid and implausible values, logged one row per issue.</div>
<div class="step"><b>Standardise</b>Clean names, a phonetic key for spelling variants, phone numbers in one format, parsed dates.</div>
<div class="step"><b>Block</b>Only compare records that share a key (name key, phone, ID, DOB), so far fewer pairs need scoring.</div>
<div class="step"><b>Score</b>Weighted similarity across 8 fields, plus rules (siblings, different IDs, name-only matches).</div>
<div class="step"><b>Merge</b>Auto-merge confident pairs, queue borderline ones for review, and build one golden record per person.</div>
</div></section>
{accuracy}
<section><h2>Where the scores fall</h2>
<p class="lede">Each candidate pair gets a 0–1 score. Pairs at or above {MATCH_AT} merge automatically, pairs from {REVIEW_AT} up to {MATCH_AT} go to
a reviewer ({_fmt(summary['review_queue'])} pairs), and everything below is kept apart.</p>
{_score_hist(scored)}</section>
<section><h2>Data-quality issues</h2><p class="lede">Records failing each rule.</p>
{_hbar(rule_rows, aria="Data-quality issues by rule", label_w=300)}</section>
<section><h2>Field completeness</h2><p class="lede">Share of records with a value.</p>
{_hbar(comp_rows, unit="%", label_w=300, aria="Field completeness")}</section>
<section><h2>Examples of merged duplicates</h2>
<p class="lede">Registrations the pipeline recognised as the same person despite different spellings, dates or phone formats.</p>
{_example_clusters(gold, raw)}</section>
<section><h2>Review queue (top 10)</h2>
<p class="lede">Borderline pairs a person should confirm, with field-by-field similarity so the reviewer can see why each pair was flagged.</p>
{_table(review, "small")}</section>
<footer>Built with Python, pandas and RapidFuzz. Outputs: golden_records.csv, dq_issues.csv, scored_pairs.csv, review_queue.csv.</footer>
</div><div id="tip" role="tooltip"></div></div><script>{JS}</script></body></html>"""
