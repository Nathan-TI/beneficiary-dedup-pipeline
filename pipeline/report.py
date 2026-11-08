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


def _threshold_chart(curve: list[dict]) -> str:
    """Precision and recall across auto-merge thresholds; JS moves the marker line."""
    W, H, left, right, top, bottom = 640, 230, 48, 70, 16, 34
    pw, ph = W - left - right, H - top - bottom
    lo = min(min(r["precision"], r["recall"]) for r in curve) * 100
    t0, t1, y0, y1 = curve[0]["t"], curve[-1]["t"], max(0.0, (lo // 10) * 10), 100.0

    def x(t):
        return left + pw * (t - t0) / (t1 - t0)

    def y(v):
        return top + ph * (1 - (max(min(v * 100, y1), y0) - y0) / (y1 - y0))

    parts = []
    for v in sorted({int(y0), int((y0 + 100) // 2), 100}):
        yy = top + ph * (1 - (v - y0) / (y1 - y0))
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 8}" y="{yy + 4}" text-anchor="end" class="ax">{v}%</text>')
    for t in (0.75, 0.80, 0.85, 0.90, 0.95):
        if t0 <= t <= t1:
            parts.append(f'<text x="{x(t)}" y="{H - 10}" text-anchor="middle" class="ax">{t:.2f}</text>')
    for key, col, name in (("precision", "var(--series-1)", "Precision"), ("recall", "var(--series-2)", "Recall")):
        pts = " ".join(f"{x(r['t']):.1f},{y(r[key]):.1f}" for r in curve)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/>')
        last = curve[-1]
        parts.append(f'<text x="{x(last["t"]) + 8}" y="{y(last[key]) + 4}" class="val">{name}</text>')
    parts.append(f'<line id="thrMarker" x1="{x(0.88)}" x2="{x(0.88)}" y1="{top}" y2="{top + ph}" class="thr"/>')
    meta = f'data-left="{left}" data-pw="{pw}" data-t0="{t0}" data-t1="{t1}"'
    return (f'<svg id="thrChart" {meta} viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Precision and recall by auto-merge threshold">{"".join(parts)}</svg>')


def _weekly_bars(weeks: list[dict]) -> str:
    W, H, left, bottom, top = 640, 200, 44, 30, 14
    pw, ph = W - left - 8, H - bottom - top
    mx = max(w["registrations"] for w in weeks)
    bw = pw / len(weeks)
    parts = [f'<line x1="{left}" x2="{W - 8}" y1="{top + ph}" y2="{top + ph}" class="grid"/>']
    for v in (mx // 2, mx):
        yy = top + ph * (1 - v / mx)
        parts.append(f'<line x1="{left}" x2="{W - 8}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{v}</text>')
    for i, w in enumerate(weeks):
        h = ph * w["registrations"] / mx
        xx = left + i * bw
        parts.append(
            f'<g class="hit" data-tip="Week of {w["week"]}: {w["registrations"]:,} registrations, '
            f'{w["duplicate_rate"]}% duplicates, {w["issue_rate"]}% with issues">'
            f'<rect x="{xx}" y="{top}" width="{bw}" height="{ph}" fill="transparent"/>'
            f'<path d="M{xx + 1},{top + ph} v-{max(h - 3, 0)} a3,3 0 0 1 3,-3 h{max(bw - 8, 1)} a3,3 0 0 1 3,3 v{max(h - 3, 0)} z" fill="var(--series-1)"/></g>')
        if i % 4 == 0:
            parts.append(f'<text x="{xx + bw / 2}" y="{H - 10}" text-anchor="middle" class="ax">{w["week"][5:]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Registrations per week">{"".join(parts)}</svg>'


def _weekly_line(weeks: list[dict]) -> str:
    W, H, left, bottom, top = 640, 200, 44, 30, 14
    pw, ph = W - left - 16, H - bottom - top
    mx = max(10, max(w["duplicate_rate"] for w in weeks) * 1.15)
    step = pw / max(len(weeks) - 1, 1)
    parts = [f'<line x1="{left}" x2="{W - 16}" y1="{top + ph}" y2="{top + ph}" class="grid"/>']
    for v in (round(mx / 2), round(mx)):
        yy = top + ph * (1 - v / mx)
        parts.append(f'<line x1="{left}" x2="{W - 16}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{v}%</text>')
    pts = [(left + i * step, top + ph * (1 - w["duplicate_rate"] / mx)) for i, w in enumerate(weeks)]
    parts.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" '
                 f'stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>')
    for (a, b), w in zip(pts, weeks):
        parts.append(f'<g class="hit" data-tip="Week of {w["week"]}: {w["duplicate_rate"]}% duplicates">'
                     f'<rect x="{a - step / 2}" y="{top}" width="{step}" height="{ph}" fill="transparent"/>'
                     f'<circle cx="{a}" cy="{b}" r="4" fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2"/></g>')
    for i, w in enumerate(weeks):
        if i % 4 == 0:
            parts.append(f'<text x="{pts[i][0]}" y="{H - 10}" text-anchor="middle" class="ax">{w["week"][5:]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Duplicate rate per week">{"".join(parts)}</svg>'


def _howto(text: str) -> str:
    return f'<details class="howto"><summary>How to read this</summary><p>{text}</p></details>'


CSS = """
.viz-root{color-scheme:light;--surface-0:#f4f3ef;--surface-1:#fcfcfb;--surface-2:#f0efec;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#7a7974;--rule:#e2e1dc;--series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;
--accent:#2a78d6;--warn:#fab219;--crit:#d03b3b;--good:#0ca30c}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#121211;
--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--rule:#2e2e2b;
--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;--accent:#3987e5}}
*{box-sizing:border-box}body{margin:0}html{scroll-behavior:smooth;scroll-padding-top:64px}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100vh}
.wrap{max-width:1000px;margin:0 auto;padding:28px 20px 80px}
nav.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--surface-0) 92%,transparent);backdrop-filter:blur(6px);
border-bottom:1px solid var(--rule)}
nav.top .in{max-width:1000px;margin:0 auto;padding:8px 20px;display:flex;gap:4px;align-items:center;overflow-x:auto;scrollbar-width:none}
nav.top a{color:var(--text-secondary);text-decoration:none;font-size:13.5px;padding:6px 10px;border-radius:7px;white-space:nowrap}
nav.top a:hover,nav.top a.on{background:var(--surface-2);color:var(--text-primary)}
nav.top .sp{flex:1}
.btn{font:inherit;font-size:13.5px;border:1px solid var(--rule);background:var(--surface-1);color:var(--text-primary);
padding:7px 12px;border-radius:8px;cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--surface-2)}.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
header h1{font-size:30px;line-height:1.2;margin:18px 0 8px;letter-spacing:-.01em}
header p{color:var(--text-secondary);margin:0;max-width:740px}
.meta{font-size:13px;color:var(--text-muted);margin-top:10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}
.tile{background:var(--surface-1);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.t-label{font-size:12px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}
.t-value{font-size:28px;font-weight:600;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.t-sub{font-size:12.5px;color:var(--text-muted)}
.group-title{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);margin:36px 0 6px}
section{background:var(--surface-1);border:1px solid var(--rule);border-radius:12px;padding:22px 22px 18px;margin:14px 0}
section h2{font-size:18px;margin:0 0 4px}section .lede{color:var(--text-secondary);margin:0 0 14px;font-size:14px}
h4{font-size:14px;margin:18px 0 6px;color:var(--text-secondary);font-weight:600}
svg{width:100%;height:auto;display:block;overflow:visible}
svg text{font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.ax{fill:var(--text-secondary)}.val{fill:var(--text-primary);font-variant-numeric:tabular-nums}
.grid{stroke:var(--rule);stroke-width:1}.thr{stroke:var(--text-secondary);stroke-width:1.5;stroke-dasharray:4 3}
.hit:hover path,.hit:hover circle{opacity:.8}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--text-secondary);margin-bottom:10px}
.lg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.tbl-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--text-secondary);font-weight:600;border-bottom:1px solid var(--rule);padding:6px 8px;white-space:nowrap}
th.sort{cursor:pointer;user-select:none}th.sort::after{content:" ↕";color:var(--text-muted);font-weight:400}
th.asc::after{content:" ↑"}th.desc::after{content:" ↓"}
td{border-bottom:1px solid var(--rule);padding:6px 8px;white-space:nowrap}table.small td,table.small th{padding:4px 8px}
td.num,th.num{text-align:right}
.minibar{display:inline-block;height:8px;border-radius:4px;background:var(--series-1);vertical-align:middle;margin-left:8px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;counter-reset:s}
@media(max-width:760px){.steps{grid-template-columns:1fr 1fr}}@media(max-width:440px){.steps{grid-template-columns:1fr}}
.step{border:1px solid var(--rule);border-radius:10px;padding:12px;font-size:13.5px;color:var(--text-secondary)}
.step b{display:block;color:var(--text-primary);font-size:14px;margin-bottom:4px}
.step b::before{counter-increment:s;content:counter(s) ". ";color:var(--text-muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:760px){.two{grid-template-columns:1fr}}
.recs{display:grid;gap:10px}
.rec{border:1px solid var(--rule);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:28px 1fr;gap:4px 10px}
.rec .n{grid-row:span 3;width:26px;height:26px;border-radius:50%;background:var(--surface-2);display:grid;place-items:center;font-weight:600;font-size:13px}
.rec b{font-size:14.5px}.rec p{margin:0;color:var(--text-secondary);font-size:13.5px}
.tags{display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--text-muted)}
.tag{border:1px solid var(--rule);border-radius:999px;padding:1px 8px}
.badge{display:inline-flex;gap:4px;align-items:center;font-size:12px;border-radius:999px;padding:1px 8px;border:1px solid var(--rule)}
.badge .dot{width:8px;height:8px;border-radius:50%}
.calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;align-items:end}
label.f{display:grid;gap:4px;font-size:13px;color:var(--text-secondary)}
input[type=number],input[type=text],input[type=email],select,textarea{font:inherit;font-size:14px;color:var(--text-primary);
background:var(--surface-0);border:1px solid var(--rule);border-radius:8px;padding:8px 10px;width:100%}
textarea{min-height:110px;resize:vertical}
input[type=range]{width:100%;accent-color:var(--accent)}
.out{background:var(--surface-2);border-radius:10px;padding:12px 14px}
.out .big{font-size:26px;font-weight:600;font-variant-numeric:tabular-nums}.out .lbl{font-size:12.5px;color:var(--text-secondary)}
.outs{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:12px 0}
.note{font-size:12.5px;color:var(--text-muted);margin-top:8px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;font-size:13px;color:var(--text-secondary)}
.toolbar select{width:auto}
details.howto{margin:-6px 0 12px;font-size:13px;color:var(--text-secondary)}
details.howto summary{cursor:pointer;color:var(--accent);width:max-content}
details.howto p{margin:6px 0 0;max-width:760px}
.fb-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:640px){.fb-grid{grid-template-columns:1fr}}
.fb-grid .full{grid-column:1/-1}
#fbStatus{font-size:13px;color:var(--text-secondary);margin-top:8px;min-height:1em}
#tip{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);font-size:12.5px;padding:6px 9px;
border-radius:6px;opacity:0;transition:opacity .08s;z-index:60;max-width:280px}
.fab{position:fixed;right:18px;bottom:18px;z-index:30;width:46px;height:46px;border-radius:50%;border:none;background:var(--accent);
color:#fff;font-size:20px;font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.drawer{position:fixed;inset:0 0 0 auto;width:min(420px,100%);background:var(--surface-1);border-left:1px solid var(--rule);z-index:50;
transform:translateX(100%);transition:transform .2s;overflow-y:auto;padding:20px 22px}
.drawer.open{transform:none}.scrim{position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:45;display:none}.scrim.open{display:block}
.drawer h3{margin:0 0 6px;font-size:18px}.drawer h4{margin:18px 0 6px}.drawer dl{margin:0;font-size:13.5px}
.drawer dt{font-weight:600;margin-top:8px}.drawer dd{margin:2px 0 0;color:var(--text-secondary)}
.drawer ul{padding-left:18px;font-size:13.5px;color:var(--text-secondary);margin:6px 0}
.x{float:right}
.tour-on{outline:3px solid var(--accent);outline-offset:4px;border-radius:12px}
#tourBox{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:55;width:min(520px,calc(100% - 32px));
background:var(--text-primary);color:var(--surface-1);border-radius:12px;padding:14px 16px;display:none;box-shadow:0 8px 30px rgba(0,0,0,.25)}
#tourBox p{margin:0 0 10px;font-size:14px}#tourBox .row{display:flex;gap:8px;justify-content:space-between;align-items:center}
#tourBox .btn{background:transparent;color:var(--surface-1);border-color:color-mix(in srgb,var(--surface-1) 40%,transparent)}
footer{color:var(--text-muted);font-size:13px;margin-top:28px}
"""


JS = r"""
const D = JSON.parse(document.getElementById('report-data').textContent);
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const fmt = n => n.toLocaleString('en-US');

// Tooltips on chart marks
const tip = $('#tip');
$$('.hit').forEach(g => {
  g.addEventListener('mousemove', e => { tip.textContent = g.dataset.tip; tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; });
  g.addEventListener('mouseleave', () => tip.style.opacity = 0);
});

// Highlight the nav link of the section in view
const links = $$('nav.top a[href^="#"]');
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) {
  links.forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id)); } }), {rootMargin: '-40% 0px -55% 0px'});
$$('.anchor').forEach(s => io.observe(s));

// Cost calculator + review workload
function calc() {
  const v = +$('#cVal').value || 0, m = +$('#cMonths').value || 0, mins = +$('#cMins').value || 0;
  $('#cSaved').textContent = '$' + fmt(Math.round(D.duplicates * v * m));
  $('#cPerCycle').textContent = '$' + fmt(Math.round(D.duplicates * v));
  $('#cHours').textContent = fmt(Math.round(D.review_pairs * mins / 60 * 10) / 10) + ' h';
}
['#cVal', '#cMonths', '#cMins'].forEach(s => $(s) && $(s).addEventListener('input', calc)); if ($('#cVal')) calc();

// Threshold explorer
if (D.curve.length) {
  const sl = $('#thr'), ch = $('#thrChart'), mk = $('#thrMarker');
  const L = +ch.dataset.left, PW = +ch.dataset.pw, T0 = +ch.dataset.t0, T1 = +ch.dataset.t1;
  function upd() {
    const t = +sl.value, r = D.curve.reduce((a, b) => Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a);
    const mins = +($('#cMins') ? $('#cMins').value : 2) || 2;
    $('#tVal').textContent = r.t.toFixed(2);
    $('#tAuto').textContent = fmt(r.auto); $('#tReview').textContent = fmt(r.review);
    $('#tP').textContent = (100 * r.precision).toFixed(1) + '%'; $('#tR').textContent = (100 * r.recall).toFixed(1) + '%';
    $('#tFP').textContent = fmt(r.fp); $('#tHours').textContent = (Math.round(r.review * mins / 6) / 10) + ' h';
    const x = L + PW * (r.t - T0) / (T1 - T0); mk.setAttribute('x1', x); mk.setAttribute('x2', x);
    const safe = D.curve.filter(c => c.fp === 0), best = safe.reduce((a, b) => b.recall > a.recall ? b : a, safe[0] || r);
    $('#tAdvice').textContent = r.fp > 0
      ? `⚠ At ${r.t.toFixed(2)} the system would wrongly merge ${fmt(r.fp)} pair(s) of different people. Raise the threshold to at least ${best.t.toFixed(2)}.`
      : r.recall < best.recall - 0.02
      ? `No wrong merges, but only ${(100 * r.recall).toFixed(1)}% of duplicates are caught automatically and ${fmt(r.review)} pairs go to reviewers. ${best.t.toFixed(2)} is safe and catches ${(100 * best.recall).toFixed(1)}%.`
      : `✓ Best balance: no wrong merges and the highest automatic catch rate (${(100 * r.recall).toFixed(1)}%).`;
  }
  sl.addEventListener('input', upd); upd();
}

// Sortable, filterable tables built from data
function table(el, rows, cols) {
  let key = null, dir = 1;
  function draw() {
    const r = key ? [...rows].sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir) : rows;
    el.querySelector('tbody').innerHTML = r.map(row => '<tr>' + cols.map(c => `<td class="${c.num ? 'num' : ''}">${c.fmt ? c.fmt(row[c.k], row) : row[c.k]}</td>`).join('') + '</tr>').join('')
      || `<tr><td colspan="${cols.length}">No rows match.</td></tr>`;
  }
  el.querySelector('thead').innerHTML = '<tr>' + cols.map(c => `<th class="sort ${c.num ? 'num' : ''}" data-k="${c.k}" tabindex="0" aria-label="Sort by ${c.label}">${c.label}</th>`).join('') + '</tr>';
  el.querySelectorAll('th').forEach(th => {
    const go = () => { const k = th.dataset.k; dir = key === k ? -dir : -1; key = k;
      el.querySelectorAll('th').forEach(t => t.classList.remove('asc', 'desc')); th.classList.add(dir > 0 ? 'asc' : 'desc'); draw(); };
    th.addEventListener('click', go); th.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  });
  draw();
  return { set(r) { rows = r; draw(); } };
}
const bar = (v, max) => `${v}%<span class="minibar" style="width:${Math.max(2, 60 * v / max)}px"></span>`;
const maxDup = Math.max(...D.woredas.map(w => w.duplicate_rate));
const wt = table($('#woredaTbl'), D.woredas, [
  {k: 'region', label: 'Region'}, {k: 'woreda', label: 'Woreda'},
  {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt}, {k: 'people', label: 'Unique people', num: 1, fmt: fmt},
  {k: 'duplicate_rate', label: 'Duplicate rate', num: 1, fmt: v => bar(v, maxDup)},
  {k: 'issue_rate', label: 'Issue rate', num: 1, fmt: v => v + '%'}, {k: 'id_coverage', label: 'National ID', num: 1, fmt: v => v + '%'}]);
$('#regionFilter').innerHTML = '<option value="">All regions</option>' + [...new Set(D.woredas.map(w => w.region))].sort().map(r => `<option>${r}</option>`).join('');
$('#regionFilter').addEventListener('change', e => wt.set(D.woredas.filter(w => !e.target.value || w.region === e.target.value)));

const flagBadge = (f, row) => f ? `<span class="badge" title="${row.reason}"><span class="dot" style="background:var(--warn)"></span>⚠ Coach</span>` : '<span class="badge"><span class="dot" style="background:var(--good)"></span>✓ OK</span>';
const et = table($('#enumTbl'), D.enumerators, [
  {k: 'enumerator_id', label: 'Enumerator'}, {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt},
  {k: 'issue_rate', label: 'Issue rate', num: 1, fmt: v => v + '%'}, {k: 'duplicate_rate', label: 'Duplicate rate', num: 1, fmt: v => v + '%'},
  {k: 'valid_phone', label: 'Valid phone', num: 1, fmt: v => v + '%'}, {k: 'flag', label: 'Status', fmt: flagBadge}]);
$('#flagOnly').addEventListener('change', e => et.set(D.enumerators.filter(r => !e.target.checked || r.flag)));

// Help drawer
const drawer = $('#help'), scrim = $('#scrim');
const openHelp = () => { drawer.classList.add('open'); scrim.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); $('#helpClose').focus(); };
const closeHelp = () => { drawer.classList.remove('open'); scrim.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); };
$$('[data-open-help]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); openHelp(); }));
$('#helpClose').addEventListener('click', closeHelp); scrim.addEventListener('click', closeHelp);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeHelp(); endTour(); } });

// Guided tour
const steps = [
  ['#overview', 'Start here: the headline numbers. Records in, unique people after removing duplicates, and how much of the data has quality problems.'],
  ['#decisions', 'The recommended actions, each with an owner. This is the short list for a management meeting.'],
  ['#cost', 'Type in your transfer value and number of months to see what removing duplicates is worth. Change the review minutes to see staff time.'],
  ['#threshold', 'Drag the slider to see the trade-off: a lower threshold merges more automatically but risks wrong merges; a higher one sends more pairs to reviewers.'],
  ['#hotspots', 'Where to focus: sort any column, or filter by region, to find locations with the most duplicates or the lowest national ID coverage.'],
  ['#enumerators', 'Which enumerators need coaching. Tick "Flagged only" to see just them.'],
  ['#quality', 'Which data-quality rules fail most, and the form change that would stop each one at the source.'],
  ['#feedback', 'Need another view, a new rule or a different breakdown? Send a request here.'],
];
let ti = -1;
function showStep(i) {
  $$('.tour-on').forEach(e => e.classList.remove('tour-on'));
  if (i < 0 || i >= steps.length) return endTour();
  ti = i; const [sel, text] = steps[i], el = $(sel);
  el.classList.add('tour-on'); el.scrollIntoView({behavior: 'smooth', block: 'start'});
  $('#tourText').textContent = text; $('#tourCount').textContent = `${i + 1} / ${steps.length}`;
  $('#tourNext').textContent = i === steps.length - 1 ? 'Finish' : 'Next'; $('#tourBox').style.display = 'block';
}
function endTour() { $$('.tour-on').forEach(e => e.classList.remove('tour-on')); $('#tourBox').style.display = 'none'; ti = -1; }
$$('[data-tour]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); closeHelp(); showStep(0); }));
$('#tourNext').addEventListener('click', () => showStep(ti + 1));
$('#tourPrev').addEventListener('click', () => showStep(Math.max(0, ti - 1)));
$('#tourEnd').addEventListener('click', endTour);

// Feedback: build a GitHub issue (no server needed) or copy the text
function fbText() {
  const v = id => $(id).value.trim();
  return { title: `[${v('#fbType')}] ${v('#fbSummary') || 'Feedback on the report'}`,
    body: [`**Type:** ${v('#fbType')}`, `**Section:** ${v('#fbSection')}`, `**Priority:** ${v('#fbPriority')}`,
      `**From:** ${v('#fbName') || 'not given'}${v('#fbRole') ? ' (' + v('#fbRole') + ')' : ''}`, '',
      '**What do you need or what did you notice?**', v('#fbDetail') || '-', '',
      '**What decision would this help you make?**', v('#fbDecision') || '-'].join('\n') };
}
$('#fbForm').addEventListener('submit', e => {
  e.preventDefault();
  if (!$('#fbDetail').value.trim()) { $('#fbStatus').textContent = 'Please describe what you need first.'; $('#fbDetail').focus(); return; }
  const t = fbText();
  const url = `https://github.com/${D.repo}/issues/new?labels=feedback&title=${encodeURIComponent(t.title)}&body=${encodeURIComponent(t.body)}`;
  $('#fbLink').href = url; $('#fbLink').style.display = 'inline-block';
  $('#fbStatus').textContent = 'Ready. Open GitHub to submit it (a free GitHub account is needed), or copy the text and email it.';
});
$('#fbCopy').addEventListener('click', async () => {
  const t = fbText();
  try { await navigator.clipboard.writeText(t.title + '\n\n' + t.body); $('#fbStatus').textContent = 'Copied. Paste it into an email or chat.'; }
  catch { $('#fbStatus').textContent = 'Copy was blocked by the browser. Select the text in the form and copy it manually.'; }
});
"""


def build(summary: dict, issues: pd.DataFrame, comp: pd.DataFrame, scored: pd.DataFrame,
          gold: pd.DataFrame, raw: pd.DataFrame, ins: dict | None = None,
          repo: str = "Nathan-TI/beneficiary-dedup-pipeline") -> str:
    import json

    ins = ins or {}
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

    data = {"repo": repo, "duplicates": ins.get("duplicates", summary["duplicates_removed"]),
            "review_pairs": summary["review_queue"], "curve": ins.get("curve", []),
            "woredas": ins.get("woredas", []), "enumerators": ins.get("enumerators", [])}
    data_json = json.dumps(data).replace("</", "<\\/")

    recs_html = "".join(
        f'<div class="rec"><span class="n">{i}</span><b>{E(r["title"])}</b><p>{E(r["detail"])}</p>'
        f'<div class="tags"><span class="tag">Owner: {E(r["owner"])}</span>'
        f'<span class="tag">Impact: {E(r["impact"])}</span></div></div>'
        for i, r in enumerate(ins.get("recommendations", []), 1))

    fixes = pd.DataFrame(ins.get("source_fixes", []))
    fixes_html = ""
    if not fixes.empty:
        fixes.columns = ["Rule", "Records", "Fix at the source"]
        fixes_html = "<h4>Stop errors at the source</h4>" + _table(fixes, "small")

    threshold_html = ""
    if data["curve"]:
        threshold_html = f"""
<section id="threshold" class="anchor"><h2>Threshold explorer: accuracy vs reviewer workload</h2>
<p class="lede">Every candidate pair gets a 0–1 match score. Choose the score above which records merge automatically, and see the effect.</p>
{_howto("Precision is the share of automatic merges that are correct (wrong merges can cut a real person off assistance). "
        "Recall is the share of all real duplicates that are caught automatically. Pairs scoring between 0.75 and the threshold "
        "go to a reviewer, so a higher threshold is safer but costs more staff time. The dashed line marks your choice.")}
<label for="thr" style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:4px">Auto-merge threshold: <b id="tVal" style="color:var(--text-primary);font-size:15px">0.88</b> <span style="color:var(--text-muted)">(current setting 0.88)</span></label>
<input id="thr" type="range" min="{data['curve'][0]['t']}" max="{data['curve'][-1]['t']}" step="0.01" value="0.88">
<div class="outs">
<div class="out"><div class="lbl">Merged automatically</div><div class="big" id="tAuto">–</div></div>
<div class="out"><div class="lbl">Sent to reviewers</div><div class="big" id="tReview">–</div></div>
<div class="out"><div class="lbl">Reviewer time</div><div class="big" id="tHours">–</div></div>
<div class="out"><div class="lbl">Precision</div><div class="big" id="tP">–</div></div>
<div class="out"><div class="lbl">Recall</div><div class="big" id="tR">–</div></div>
<div class="out"><div class="lbl">Wrong merges</div><div class="big" id="tFP">–</div></div>
</div>
<p id="tAdvice" style="margin:4px 0 12px;font-weight:500"></p>
<div class="legend"><span class="lg"><i style="background:var(--series-1)"></i>Precision</span><span class="lg"><i style="background:var(--series-2)"></i>Recall</span></div>
{_threshold_chart(data['curve'])}</section>"""

    accuracy = ""
    if metrics:
        b, p, r = metrics["baseline"], metrics["pipeline"], metrics["pipeline_after_review"]
        accuracy = f"""
<section id="accuracy" class="anchor"><h2>Accuracy against ground truth</h2>
<p class="lede">The data is synthetic, so every true duplicate is known and accuracy can be measured rather than guessed.
Exact matching finds only {100 * b['recall']:.0f}% of duplicate pairs. Fuzzy matching with domain rules finds
{100 * p['recall']:.1f}% automatically with {p['fp']} false merges, and {100 * r['recall']:.1f}% once the review queue is worked.</p>
{_accuracy_chart(metrics)}</section>"""

    weeks = ins.get("weekly", [])
    trend_html = ""
    if len(weeks) > 2:
        trend_html = f"""
<section id="trend" class="anchor"><h2>Registration trend</h2>
<p class="lede">Weekly volume and the share of registrations that re-register someone already on the list. A rising line is an early warning: check new registrations against the existing list at the point of registration, or pause and verify.</p>
{_howto("Hover over a week to see its exact numbers. The two charts share the same weeks, so read them top to bottom.")}
<div class="two"><div><h4>Registrations per week</h4>{_weekly_bars(weeks)}</div>
<div><h4>Duplicate rate per week</h4>{_weekly_line(weeks)}</div></div></section>"""

    help_drawer = """
<div id="scrim" class="scrim"></div>
<aside id="help" class="drawer" aria-hidden="true" aria-label="Help">
<button class="btn x" id="helpClose" aria-label="Close help">Close ✕</button>
<h3>How to use this report</h3>
<p style="color:var(--text-secondary);font-size:13.5px;margin:0">About 5 minutes to read. Everything runs in your browser, and nothing you type is sent anywhere unless you choose to submit feedback.</p>
<p><button class="btn primary" data-tour>Take the 1-minute tour</button></p>
<h4>Quick start</h4>
<ul><li><b>Managers:</b> read <i>Decisions</i>, then try the <i>cost calculator</i> with your own transfer value.</li>
<li><b>IM / data teams:</b> use the <i>threshold explorer</i>, <i>hotspots</i> and <i>enumerator</i> tables.</li>
<li><b>Field coordinators:</b> go to <i>Enumerators</i> and tick "Flagged only".</li></ul>
<h4>Ways to interact</h4>
<ul><li>Hover over any bar, dot or line to see exact values.</li>
<li>Click a table header to sort it, and click again to reverse the order.</li>
<li>Use the region filter and the "Flagged only" box to narrow the tables.</li>
<li>Type into the calculator boxes, or drag the threshold slider, and the numbers update straight away.</li>
<li>Open "How to read this" under any section title for a plain-language explanation.</li></ul>
<h4>Glossary</h4>
<dl>
<dt>Duplicate</dt><dd>A registration for someone who is already on the list.</dd>
<dt>Golden record</dt><dd>The single, most complete record kept for each real person after merging duplicates.</dd>
<dt>Match score</dt><dd>0–1 similarity between two records across names, date of birth, phone, ID, sex and location.</dd>
<dt>Review queue</dt><dd>Borderline pairs a person should confirm before merging.</dd>
<dt>Precision</dt><dd>Of the pairs merged, the share that really are the same person. 100% means no one was wrongly merged.</dd>
<dt>Recall</dt><dd>Of all real duplicates, the share that were found.</dd>
<dt>Blocking</dt><dd>Only comparing records that share a key (such as phone or name sound), so millions of comparisons are skipped.</dd>
<dt>Data-quality rule</dt><dd>A check such as "phone number has the right format". Critical rules block use of the record; warnings need a fix.</dd>
</dl>
<h4>FAQ</h4>
<dl>
<dt>Is this real data?</dt><dd>No. Every record is synthetic. No real person is represented.</dd>
<dt>Can it run on our data?</dt><dd>Yes: <code>python run_pipeline.py --input your_file.csv</code>. Accuracy scores need known answers, so they only appear for synthetic data.</dd>
<dt>Who decides the thresholds?</dt><dd>The programme. The explorer shows the trade-off, so the choice can be agreed and documented.</dd>
<dt>Something is missing or wrong?</dt><dd><a href="#feedback" onclick="document.getElementById('helpClose').click()">Send feedback</a>, and it becomes a tracked request.</dd>
</dl></aside>
<button class="fab" data-open-help aria-label="Open help">?</button>
<div id="tourBox" role="dialog" aria-live="polite"><p id="tourText"></p>
<div class="row"><span id="tourCount" style="font-size:12.5px;opacity:.8"></span>
<span style="display:flex;gap:8px"><button class="btn" id="tourEnd">Skip</button><button class="btn" id="tourPrev">Back</button>
<button class="btn" id="tourNext">Next</button></span></div></div>"""

    feedback = """
<section id="feedback" class="anchor"><h2>Feedback and new requirements</h2>
<p class="lede">Tell us what else you need: a new breakdown, a different rule, an export, or something that looks wrong.
Each request becomes a tracked issue on GitHub, so you can follow its progress.</p>
<form id="fbForm" class="fb-grid" novalidate>
<label class="f">Your name (optional)<input id="fbName" type="text" autocomplete="name"></label>
<label class="f">Role / organisation (optional)<input id="fbRole" type="text" placeholder="e.g. Programme Officer, Area office"></label>
<label class="f">Type of feedback<select id="fbType">
<option>New requirement</option><option>New insight or breakdown</option><option>Data issue</option>
<option>Question</option><option>Bug</option><option>Other</option></select></label>
<label class="f">Section<select id="fbSection">
<option>Whole report</option><option>Decisions</option><option>Cost calculator</option><option>Threshold explorer</option>
<option>Registration trend</option><option>Location hotspots</option><option>Enumerators</option><option>Data quality</option>
<option>Duplicates / review queue</option></select></label>
<label class="f">Priority<select id="fbPriority"><option>Nice to have</option><option>Important</option><option>Blocking a decision</option></select></label>
<label class="f">One-line summary<input id="fbSummary" type="text" placeholder="e.g. Duplicate rate by kebele"></label>
<label class="f full">What do you need, or what did you notice? *<textarea id="fbDetail" required placeholder="Describe the requirement or issue"></textarea></label>
<label class="f full">What decision would this help you make? (optional)<input id="fbDecision" type="text" placeholder="e.g. Where to send verification teams next month"></label>
<div class="full" style="display:flex;gap:10px;flex-wrap:wrap">
<button class="btn primary" type="submit">Prepare request</button>
<a id="fbLink" class="btn" href="#" target="_blank" rel="noopener" style="display:none;text-decoration:none">Open on GitHub ↗</a>
<button class="btn" type="button" id="fbCopy">Copy text</button></div>
</form><div id="fbStatus" role="status"></div></section>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beneficiary Deduplication &amp; Data-Quality Pipeline — Report</title><style>{CSS}</style></head>
<body><div class="viz-root">
<nav class="top" aria-label="Sections"><div class="in">
<a href="#overview">Overview</a><a href="#decisions">Decisions</a><a href="#cost">Insights</a><a href="#quality">Data quality</a>
<a href="#duplicates">Duplicates</a><a href="#method">How it works</a><a href="#feedback">Feedback</a><span class="sp"></span>
<button class="btn" data-tour>Tour</button><button class="btn" data-open-help>Help</button></div></nav>
<div class="wrap">
<header id="overview" class="anchor"><h1>Beneficiary Deduplication &amp; Data-Quality Pipeline</h1>
<p>Checks registration data for quality problems, finds people registered more than once (even with different spellings,
mistyped dates or phone formats), and turns the results into decisions for programme management.</p>
<div class="meta">All data is synthetic, and no real person is represented · Run {date.today().isoformat()} · {summary['runtime_s']}s runtime ·
New here? <a href="#" data-tour style="color:var(--accent)">Take the 1-minute tour</a></div></header>
<div class="tiles">{_kpis(summary)}</div>

<div class="group-title">For decision-makers</div>
<section id="decisions" class="anchor"><h2>Key findings and recommended actions</h2>
<p class="lede">Generated from this run's data. Each action has a suggested owner.</p>
{_howto("Actions are ordered by expected impact. The numbers update automatically every time the pipeline runs, so this list always reflects the latest registration data.")}
<div class="recs">{recs_html}</div></section>

<section id="cost" class="anchor"><h2>What removing duplicates is worth</h2>
<p class="lede">Enter your own values. Results are estimates of assistance that would otherwise go to duplicate registrations.</p>
{_howto("Cost avoided = duplicate registrations × transfer value per person per month × months. Reviewer time = pairs in the review queue × minutes per pair. The defaults are illustrative, so change them to match your programme.")}
<div class="calc">
<label class="f">Transfer value per person per month (USD)<input id="cVal" type="number" min="0" step="1" value="25"></label>
<label class="f">Months of assistance<input id="cMonths" type="number" min="0" step="1" value="6"></label>
<label class="f">Reviewer minutes per pair<input id="cMins" type="number" min="0" step="0.5" value="2"></label></div>
<div class="outs">
<div class="out"><div class="lbl">Cost avoided over the period</div><div class="big" id="cSaved">–</div></div>
<div class="out"><div class="lbl">Cost avoided per monthly cycle</div><div class="big" id="cPerCycle">–</div></div>
<div class="out"><div class="lbl">Staff time to clear the review queue</div><div class="big" id="cHours">–</div></div></div>
<p class="note">Based on {_fmt(data['duplicates'])} duplicate registrations and {_fmt(data['review_pairs'])} pairs needing review.</p></section>

{threshold_html}
{trend_html}

<section id="hotspots" class="anchor"><h2>Location hotspots</h2>
<p class="lede">Where duplicates and data problems concentrate, and where national ID coverage is low.</p>
{_howto("Sorted by duplicate rate. Click any header to re-sort, or filter by region. A high duplicate rate with low national ID coverage is the strongest case for a verification exercise or national ID enrolment.")}
<div class="toolbar"><label>Region <select id="regionFilter" aria-label="Filter by region"></select></label></div>
<div class="tbl-wrap"><table id="woredaTbl"><thead></thead><tbody></tbody></table></div></section>

<section id="enumerators" class="anchor"><h2>Enumerator performance</h2>
<p class="lede">Flags enumerators whose issue or duplicate rate is well above the team average (more than 1.5 standard deviations).</p>
{_howto("Use this to target coaching, not to blame. A high duplicate rate can also mean an enumerator worked in an area with repeated registrations. Hover over a status badge to see why it was flagged.")}
<div class="toolbar"><label><input type="checkbox" id="flagOnly"> Flagged only</label></div>
<div class="tbl-wrap"><table id="enumTbl"><thead></thead><tbody></tbody></table></div></section>

<div class="group-title">Data quality</div>
<section id="quality" class="anchor"><h2>Data-quality issues</h2><p class="lede">Records failing each rule, and how to prevent each one.</p>
{_howto("Critical issues stop a record from being used until it's fixed. Warnings should be corrected but don't block assistance. The table below gives the form change that prevents each error.")}
{_hbar(rule_rows, aria="Data-quality issues by rule", label_w=300)}
{fixes_html}</section>
<section id="completeness" class="anchor"><h2>Field completeness</h2><p class="lede">Share of records with a value.</p>
{_hbar(comp_rows, unit="%", label_w=300, aria="Field completeness")}</section>

<div class="group-title">Duplicates in detail</div>
<div id="duplicates" class="anchor"></div>
{accuracy}
<section id="scores" class="anchor"><h2>Where the scores fall</h2>
<p class="lede">Pairs at or above {MATCH_AT} merge automatically, pairs from {REVIEW_AT} up to {MATCH_AT} go to a reviewer
({_fmt(summary['review_queue'])} pairs), and everything below is kept apart.</p>
{_score_hist(scored)}</section>
<section id="examples" class="anchor"><h2>Examples of merged duplicates</h2>
<p class="lede">Registrations recognised as the same person despite different spellings, dates or phone formats.</p>
{_example_clusters(gold, raw)}</section>
<section id="review" class="anchor"><h2>Review queue (top 10)</h2>
<p class="lede">Borderline pairs a person should confirm, with field-by-field similarity (1.0 = identical, blank = missing on one side).</p>
{_table(review, "small")}</section>

<div class="group-title">Method</div>
<section id="method" class="anchor"><h2>How it works</h2><p class="lede">The same steps a registration team follows before a distribution list goes out.</p>
<div class="steps">
<div class="step"><b>Generate</b>Synthetic registrations with planted duplicates, sibling look-alikes and typical field errors.</div>
<div class="step"><b>Check quality</b>{len(by_rule)} rules for missing, invalid and implausible values, logged one row per issue.</div>
<div class="step"><b>Standardise</b>Clean names, a phonetic key for spelling variants, phone numbers in one format, parsed dates.</div>
<div class="step"><b>Block</b>Only compare records that share a key (name key, phone, ID, DOB), so far fewer pairs need scoring.</div>
<div class="step"><b>Score</b>Weighted similarity across 8 fields, plus rules (siblings, different IDs, name-only matches).</div>
<div class="step"><b>Merge &amp; model</b>Auto-merge confident pairs, queue borderline ones, build golden records, and model the results in dbt.</div>
</div></section>
{feedback}
<footer>Built with Python, pandas, RapidFuzz and dbt. Source and documentation:
<a href="https://github.com/{repo}" style="color:var(--accent)">github.com/{repo}</a></footer>
</div>
{help_drawer}
<div id="tip" role="tooltip"></div></div>
<script type="application/json" id="report-data">{data_json}</script>
<script>{JS}</script></body></html>"""
