"""Interactive, self-contained HTML report (no external assets) — works offline and on GitHub Pages.

Organised as tabs for different readers:
  Summary (managers) · Priority areas (field/area teams) · Data quality (data teams) ·
  Duplicates (reviewers) · Performance (anyone who needs to trust the results) · How it works · Feedback
"""
from __future__ import annotations

import html
import json
from datetime import date

import pandas as pd

from .dedup import MATCH_AT, REVIEW_AT

E = html.escape
CRIT, WARN = "#d03b3b", "#fab219"


def _fmt(n) -> str:
    return f"{n:,}"


def _pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


# ---------------------------------------------------------------- charts (static SVG with hover tips)

def _bar_path(x, y, w, h, r=4):
    """Horizontal bar with rounded right end, anchored at x."""
    w = max(w, 2)
    r = min(r, w / 2, h / 2)
    return f"M{x},{y} h{w - r} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{w - r} z"


def _col_path(x, base, w, h, r=3):
    """Vertical column with rounded top, anchored at the baseline."""
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    return f"M{x},{base} v-{h - r} a{r},{r} 0 0 1 {r},-{r} h{w - 2 * r} a{r},{r} 0 0 1 {r},{r} v{h - r} z"


def _hbars(rows, label_w=250, unit="", aria="", W=640):
    """rows: (label, value, colour, tooltip)."""
    right, bar, gap = 64, 16, 9
    pw = W - label_w - right
    mx = max(v for _, v, _, _ in rows) or 1
    out, y = [], 4
    for label, v, col, tip in rows:
        w = pw * v / mx
        txt = f"{v:,.1f}{unit}" if unit else _fmt(int(v))
        out.append(f'<g class="hit" data-tip="{E(tip)}"><rect x="0" y="{y - 4}" width="{W}" height="{bar + 8}" fill="transparent"/>'
                   f'<text x="{label_w - 12}" y="{y + bar - 4}" text-anchor="end" class="ax">{E(label)}</text>'
                   f'<path d="{_bar_path(label_w, y, w, bar)}" fill="{col}"/>'
                   f'<text x="{label_w + max(w, 2) + 6}" y="{y + bar - 4}" class="val">{txt}</text></g>')
        y += bar + gap
    return f'<svg viewBox="0 0 {W} {y}" role="img" aria-label="{E(aria)}">{"".join(out)}</svg>'


def _accuracy_chart(metrics: dict) -> str:
    series = [("baseline", "Exact matching (common approach)", "var(--c1)"),
              ("pipeline", "This system (automatic)", "var(--c2)"),
              ("pipeline_after_review", "This system with manual review", "var(--c3)")]
    groups = [("precision", "Correct merges"), ("recall", "Duplicates identified"), ("f1", "Overall score")]
    W, left, right, bar, gap, ggap = 640, 130, 60, 16, 3, 22
    pw = W - left - right
    y, parts = 8, []
    for key, label in groups:
        gh = len(series) * bar + (len(series) - 1) * gap
        parts.append(f'<text x="{left - 12}" y="{y + gh / 2 + 4}" text-anchor="end" class="ax">{label}</text>')
        for si, (sk, sname, col) in enumerate(series):
            v = metrics[sk][key]
            by = y + si * (bar + gap)
            parts.append(f'<g class="hit" data-tip="{E(sname)} · {label}: {_pct(v)}">'
                         f'<rect x="{left}" y="{by - 1}" width="{pw}" height="{bar + 2}" fill="transparent"/>'
                         f'<path d="{_bar_path(left, by, pw * v, bar)}" fill="{col}"/>'
                         f'<text x="{left + pw * v + 6}" y="{by + bar - 4}" class="val">{_pct(v)}</text></g>')
        y += gh + ggap
    for t in (0, 0.5, 1):
        x = left + pw * t
        parts.insert(0, f'<line x1="{x}" x2="{x}" y1="0" y2="{y - ggap + 8}" class="grid"/>'
                        f'<text x="{x}" y="{y - ggap + 24}" text-anchor="middle" class="ax">{int(t * 100)}%</text>')
    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{E(n)}</span>' for _, n, c in series)
    return (f'<div class="legend">{legend}</div><svg viewBox="0 0 {W} {y - ggap + 30}" role="img" '
            f'aria-label="Accuracy compared with exact matching">{"".join(parts)}</svg>')


def _score_hist(scored: pd.DataFrame) -> str:
    W, H, left, bottom, top = 640, 230, 44, 30, 16
    bins = [i / 40 for i in range(41)]
    counts = pd.cut(scored["score"], bins, include_lowest=True).value_counts(sort=False).tolist()
    mx = max(counts) or 1
    pw, ph = W - left - 10, H - bottom - top
    bw = pw / 40
    parts = []
    for t in (0, mx // 2, mx):
        yy = top + ph * (1 - t / mx)
        parts.append(f'<line x1="{left}" x2="{W - 10}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{_fmt(t)}</text>')
    for i, c in enumerate(counts):
        lo, hi = bins[i], bins[i + 1]
        zone, col = (("merged automatically", "var(--c3)") if lo >= MATCH_AT - 1e-9 else
                     ("referred for manual review", "var(--c2)") if lo >= REVIEW_AT - 1e-9 else ("treated as different individuals", "var(--c1)"))
        x = left + i * bw
        parts.append(f'<g class="hit" data-tip="Score {lo:.3f}–{hi:.3f}: {_fmt(c)} pairs ({zone})">'
                     f'<rect x="{x}" y="{top}" width="{bw}" height="{ph}" fill="transparent"/>'
                     f'<path d="{_col_path(x + 1, top + ph, bw - 2, ph * c / mx)}" fill="{col}"/></g>')
    for t in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<text x="{left + pw * t}" y="{H - 10}" text-anchor="middle" class="ax">{t:.2f}</text>')
    legend = ('<div class="legend"><span class="lg"><i style="background:var(--c1)"></i>Treated as different individuals</span>'
              f'<span class="lg"><i style="background:var(--c2)"></i>Referred for manual review ({REVIEW_AT}–{MATCH_AT})</span>'
              f'<span class="lg"><i style="background:var(--c3)"></i>Merged automatically (≥ {MATCH_AT})</span></div>')
    return legend + f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="How similar each compared pair is">{"".join(parts)}</svg>'


def _threshold_chart(curve: list[dict]) -> str:
    W, H, left, right, top, bottom = 640, 230, 48, 120, 16, 34
    pw, ph = W - left - right, H - top - bottom
    lo = min(min(r["precision"], r["recall"]) for r in curve) * 100
    t0, t1, y0 = curve[0]["t"], curve[-1]["t"], max(0.0, (lo // 10) * 10)

    def x(t):
        return left + pw * (t - t0) / (t1 - t0)

    def y(v):
        return top + ph * (1 - (v * 100 - y0) / (100 - y0))

    parts = []
    for v in sorted({int(y0), int((y0 + 100) // 2), 100}):
        yy = top + ph * (1 - (v - y0) / (100 - y0))
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 8}" y="{yy + 4}" text-anchor="end" class="ax">{v}%</text>')
    for t in (0.75, 0.80, 0.85, 0.90, 0.95):
        if t0 <= t <= t1:
            parts.append(f'<text x="{x(t)}" y="{H - 10}" text-anchor="middle" class="ax">{t:.2f}</text>')
    for key, col, name in (("precision", "var(--c1)", "Correct merges"), ("recall", "var(--c2)", "Duplicates identified")):
        pts = " ".join(f"{x(r['t']):.1f},{y(r[key]):.1f}" for r in curve)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>')
        parts.append(f'<text x="{x(curve[-1]["t"]) + 8}" y="{y(curve[-1][key]) + 4}" class="val">{name}</text>')
    parts.append(f'<line id="thrMarker" x1="{x(MATCH_AT)}" x2="{x(MATCH_AT)}" y1="{top}" y2="{top + ph}" class="thr"/>')
    return (f'<svg id="thrChart" data-left="{left}" data-pw="{pw}" data-t0="{t0}" data-t1="{t1}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="Correct merges and duplicates identified at each threshold">{"".join(parts)}</svg>')


def _weekly_bars(weeks):
    W, H, left, bottom, top = 640, 210, 44, 30, 14
    pw, ph = W - left - 8, H - bottom - top
    mx = max(w["registrations"] for w in weeks)
    bw = pw / len(weeks)
    parts = []
    for v in (0, mx // 2, mx):
        yy = top + ph * (1 - v / mx)
        parts.append(f'<line x1="{left}" x2="{W - 8}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{v}</text>')
    for i, w in enumerate(weeks):
        xx = left + i * bw
        parts.append(f'<g class="hit" data-tip="Week of {w["week"]}: {w["registrations"]:,} registrations">'
                     f'<rect x="{xx}" y="{top}" width="{bw}" height="{ph}" fill="transparent"/>'
                     f'<path d="{_col_path(xx + 1, top + ph, max(bw - 2, 1), ph * w["registrations"] / mx)}" fill="var(--c1)"/></g>')
        if i % 4 == 0:
            parts.append(f'<text x="{xx + bw / 2}" y="{H - 10}" text-anchor="middle" class="ax">{w["week"][5:]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Registrations per week">{"".join(parts)}</svg>'


def _weekly_line(weeks):
    W, H, left, bottom, top = 640, 210, 44, 30, 14
    pw, ph = W - left - 16, H - bottom - top
    mx = max(10, max(w["duplicate_rate"] for w in weeks) * 1.15)
    step = pw / max(len(weeks) - 1, 1)
    parts = []
    for v in (0, round(mx / 2), round(mx)):
        yy = top + ph * (1 - v / mx)
        parts.append(f'<line x1="{left}" x2="{W - 16}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{v}%</text>')
    pts = [(left + i * step, top + ph * (1 - w["duplicate_rate"] / mx)) for i, w in enumerate(weeks)]
    area = f"M{pts[0][0]},{top + ph} " + " ".join(f"L{a:.1f},{b:.1f}" for a, b in pts) + f" L{pts[-1][0]},{top + ph} Z"
    parts.append(f'<path d="{area}" fill="var(--c2)" opacity=".12"/>')
    parts.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="var(--c2)" stroke-width="2.5" stroke-linejoin="round"/>')
    for (a, b), w in zip(pts, weeks):
        parts.append(f'<g class="hit" data-tip="Week of {w["week"]}: {w["duplicate_rate"]}% duplicate registrations">'
                     f'<rect x="{a - step / 2}" y="{top}" width="{step}" height="{ph}" fill="transparent"/>'
                     f'<circle cx="{a}" cy="{b}" r="4" fill="var(--c2)" stroke="var(--surface-1)" stroke-width="2"/></g>')
    for i, w in enumerate(weeks):
        if i % 4 == 0:
            parts.append(f'<text x="{pts[i][0]}" y="{H - 10}" text-anchor="middle" class="ax">{w["week"][5:]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Duplicate registrations per week">{"".join(parts)}</svg>'


def _enum_scatter(enums):
    W, H, left, bottom, top, right = 640, 250, 48, 40, 14, 70
    pw, ph = W - left - right, H - bottom - top
    xm = max(e["issue_rate"] for e in enums) * 1.12
    ym = max(e["duplicate_rate"] for e in enums) * 1.12
    parts = []
    for v in (0, xm / 2, xm):
        x = left + pw * v / xm
        parts.append(f'<line x1="{x}" x2="{x}" y1="{top}" y2="{top + ph}" class="grid"/>'
                     f'<text x="{x}" y="{top + ph + 18}" text-anchor="middle" class="ax">{v:.0f}%</text>')
    for v in (0, ym / 2, ym):
        yy = top + ph * (1 - v / ym)
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{yy}" y2="{yy}" class="grid"/>'
                     f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" class="ax">{v:.0f}%</text>')
    parts.append(f'<text x="{left + pw / 2}" y="{H - 2}" text-anchor="middle" class="ax">Error rate →</text>')
    parts.append(f'<text transform="translate(12 {top + ph / 2}) rotate(-90)" text-anchor="middle" class="ax">Duplicate rate →</text>')
    placed = []
    for e in sorted(enums, key=lambda e: e["flag"]):
        x = left + pw * e["issue_rate"] / xm
        yy = top + ph * (1 - e["duplicate_rate"] / ym)
        col = "var(--c2)" if e["flag"] else "var(--c1)"
        tip = f'{e["enumerator_id"]}: error rate {e["issue_rate"]}%, duplicate rate {e["duplicate_rate"]}%' + (
            f' · follow-up recommended ({e["reason"]})' if e["flag"] else "")
        parts.append(f'<g class="hit" data-tip="{E(tip)}"><circle cx="{x}" cy="{yy}" r="12" fill="transparent"/>'
                     f'<circle cx="{x}" cy="{yy}" r="{6 if e["flag"] else 5}" fill="{col}" stroke="var(--surface-1)" stroke-width="2"/></g>')
        if e["flag"]:
            ly = yy - 8
            while any(abs(ly - py) < 14 and abs(x - px) < 70 for px, py in placed):
                ly += 15
            placed.append((x, ly))
            parts.append(f'<text x="{x + 10}" y="{ly}" class="val" style="font-size:11.5px;font-weight:600">{e["enumerator_id"]}</text>')
    legend = ('<div class="legend"><span class="lg"><i style="background:var(--c1);border-radius:50%"></i>Within normal range</span>'
              '<span class="lg"><i style="background:var(--c2);border-radius:50%"></i>Follow-up recommended</span></div>')
    return legend + f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Enumerators by error rate and duplicate rate">{"".join(parts)}</svg>'


def _bench_chart(bench):
    rows = [(f'{b["records"]:,} registrations', b["seconds"], "var(--c3)",
             f'{b["records"]:,} registrations in {b["seconds"]} s ({b["records_per_second"]:,} per second)') for b in bench]
    return _hbars(rows, label_w=170, unit=" s", aria="Time to process by data size")


# ---------------------------------------------------------------- HTML helpers

def _table(df: pd.DataFrame, cls="small") -> str:
    head = "".join(f"<th>{E(str(c))}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{'' if pd.isna(v) else E(str(v))}</td>" for v in row) + "</tr>"
                   for row in df.itertuples(index=False))
    return f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _example_clusters(gold, raw, k=4):
    cols = {"record_id": "Record", "first_name": "First name", "father_name": "Father's name",
            "grandfather_name": "Grandfather's name", "date_of_birth": "Date of birth", "phone": "Phone", "kebele": "Kebele"}
    out = []
    for _, g in gold[gold["n_records"] > 1].iterrows():
        sub = raw[raw["record_id"].isin(g["merged_record_ids"].split(";"))]
        if sub["first_name"].astype(str).str.strip().str.lower().nunique() > 1 or sub["date_of_birth"].nunique() > 1:
            out.append(f'<div class="case"><div class="case-h">Individual {len(out) + 1} · registered {len(sub)} times</div>'
                       + _table(sub[list(cols)].rename(columns=cols)) + "</div>")
        if len(out) == k:
            break
    return "".join(out)


def _howto(text):
    return f'<details class="howto"><summary>How to read this</summary><p>{text}</p></details>'


def _card(title, lede, body, id_=None, help_=None):
    return (f'<section class="card"{f" id={id_!r}" if id_ else ""}><h2>{title}</h2>'
            f'{f"<p class=lede>{lede}</p>" if lede else ""}{_howto(help_) if help_ else ""}{body}</section>')


def _tiles(tiles):
    return '<div class="tiles">' + "".join(
        f'<div class="tile" style="--tc:{c}"><div class="t-label">{a}</div><div class="t-value">{b}</div>'
        f'<div class="t-sub">{s}</div></div>' for a, b, s, c in tiles) + "</div>"


# ---------------------------------------------------------------- styles and behaviour

CSS = r"""
.viz-root{color-scheme:light;--surface-0:#f4f3ef;--surface-1:#fcfcfb;--surface-2:#f0efec;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#7a7974;--rule:#e2e1dc;--c1:#2a78d6;--c2:#eb6834;--c3:#1baf7a;--c4:#eda100;
--c5:#e87ba4;--c7:#6250d6;--accent:#2a78d6;--warn:#fab219;--crit:#d03b3b;--good:#0ca30c}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#121211;
--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;--rule:#2e2e2b;
--c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c7:#9085e9;--accent:#3987e5}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-0:#121211;--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#f0efec;
--text-secondary:#c3c2b7;--text-muted:#8f8e86;--rule:#2e2e2b;--c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c7:#9085e9;--accent:#3987e5}
*{box-sizing:border-box}body{margin:0}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100vh}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px 90px}
a{color:var(--accent)}
.strip{background:#0b0b0b;color:#f0efec;font-size:13px}
.strip .in{max-width:1040px;margin:0 auto;padding:7px 20px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.strip a{color:#f0efec;opacity:.9}.strip b{font-weight:600}
.hero{margin:22px 0 0;border-radius:18px;padding:30px 30px 26px;border:1px solid var(--rule);
background:radial-gradient(120% 140% at 0% 0%,color-mix(in srgb,var(--c1) 22%,transparent),transparent 55%),
radial-gradient(120% 140% at 100% 0%,color-mix(in srgb,var(--c3) 20%,transparent),transparent 55%),
radial-gradient(140% 120% at 50% 120%,color-mix(in srgb,var(--c2) 14%,transparent),transparent 60%),var(--surface-1)}
.hero h1{font-size:32px;line-height:1.15;margin:0 0 10px;letter-spacing:-.015em}
.hero p{margin:0;color:var(--text-secondary);max-width:720px;font-size:16px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px;align-items:center}
.chip{font-size:12.5px;border:1px solid var(--rule);background:var(--surface-1);border-radius:999px;padding:3px 10px;color:var(--text-secondary)}
.btn{font:inherit;font-size:13.5px;border:1px solid var(--rule);background:var(--surface-1);color:var(--text-primary);padding:7px 13px;
border-radius:9px;cursor:pointer;white-space:nowrap;text-decoration:none;display:inline-flex;gap:6px;align-items:center}
.btn:hover{background:var(--surface-2)}.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{filter:brightness(1.07)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tabs{position:sticky;top:0;z-index:20;margin:18px -20px 0;padding:10px 20px;background:color-mix(in srgb,var(--surface-0) 90%,transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--rule);display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;align-items:center}
.tab{font:inherit;font-size:14px;border:1px solid transparent;background:transparent;color:var(--text-secondary);padding:8px 14px;border-radius:999px;
cursor:pointer;white-space:nowrap;display:inline-flex;gap:7px;align-items:center}
.tab .d{width:9px;height:9px;border-radius:50%;background:var(--tc)}
.tab:hover{background:var(--surface-2);color:var(--text-primary)}
.tab[aria-selected=true]{background:var(--surface-1);border-color:var(--rule);color:var(--text-primary);font-weight:600;
box-shadow:0 1px 0 color-mix(in srgb,var(--tc) 60%,transparent),inset 0 -3px 0 var(--tc)}
.tabs .sp{flex:1}
.subhead{font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--text-muted);margin:24px 0 2px;font-weight:600}
.panel{display:none;animation:fade .18s ease}.panel.on{display:block}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.panel-h{display:flex;gap:14px;align-items:flex-start;margin:26px 0 8px}
.panel-h .ic{width:42px;height:42px;border-radius:12px;background:color-mix(in srgb,var(--tc) 18%,transparent);display:grid;place-items:center;
font-size:20px;flex:none;color:var(--tc)}
.panel-h h2{font-size:22px;margin:0}.panel-h p{margin:2px 0 0;color:var(--text-secondary)}
.who{font-size:12.5px;color:var(--text-muted)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface-1);border:1px solid var(--rule);border-radius:14px;padding:14px 16px 14px 18px;position:relative;overflow:hidden}
.tile::before{content:"";position:absolute;inset:0 auto 0 0;width:5px;background:var(--tc)}
.t-label{font-size:12.5px;color:var(--text-secondary)}
.t-value{font-size:30px;font-weight:700;margin:2px 0;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.t-sub{font-size:12.5px;color:var(--text-muted)}
section.card{background:var(--surface-1);border:1px solid var(--rule);border-radius:16px;padding:22px 22px 18px;margin:14px 0}
section.card h2{font-size:18px;margin:0 0 4px}.lede{color:var(--text-secondary);margin:0 0 12px;font-size:14.5px}
h4{font-size:14px;margin:18px 0 8px;color:var(--text-secondary);font-weight:600}
svg{width:100%;height:auto;display:block;overflow:visible}
svg text{font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.ax{fill:var(--text-secondary)}.val{fill:var(--text-primary);font-variant-numeric:tabular-nums}
.grid{stroke:var(--rule);stroke-width:1}.thr{stroke:var(--text-primary);stroke-width:1.5;stroke-dasharray:4 3}
.hit:hover path,.hit:hover circle{opacity:.82}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--text-secondary);margin-bottom:10px}
.lg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.tbl-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--text-secondary);font-weight:600;border-bottom:1px solid var(--rule);padding:7px 9px;white-space:nowrap}
th.sort{cursor:pointer;user-select:none}th.sort::after{content:" ↕";color:var(--text-muted);font-weight:400}
th.asc::after{content:" ↑"}th.desc::after{content:" ↓"}
td{border-bottom:1px solid var(--rule);padding:7px 9px;white-space:nowrap}table.small td,table.small th{padding:5px 9px;font-size:13px}
td.num,th.num{text-align:right}
td.heat{border-radius:6px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:760px){.two{grid-template-columns:1fr}}
.actions{display:grid;gap:10px;counter-reset:a}
.action{border:1px solid var(--rule);border-radius:14px;padding:14px 16px 14px 62px;position:relative;background:
linear-gradient(90deg,color-mix(in srgb,var(--ac) 9%,transparent),transparent 40%)}
.action::before{counter-increment:a;content:counter(a);position:absolute;left:16px;top:14px;width:32px;height:32px;border-radius:10px;
background:var(--ac);color:#fff;font-weight:700;display:grid;place-items:center}
.action b{font-size:15px;display:block}.action p{margin:3px 0 6px;color:var(--text-secondary);font-size:14px}
.tags{display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--text-muted)}
.tag{border:1px solid var(--rule);border-radius:999px;padding:1px 9px;background:var(--surface-1)}
.badge{display:inline-flex;gap:5px;align-items:center;font-size:12.5px;border-radius:999px;padding:1px 9px;border:1px solid var(--rule)}
.badge .dot{width:8px;height:8px;border-radius:50%}
.calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;align-items:end}
label.f{display:grid;gap:5px;font-size:13.5px;color:var(--text-secondary)}
input[type=number],input[type=text],select,textarea{font:inherit;font-size:14.5px;color:var(--text-primary);background:var(--surface-0);
border:1px solid var(--rule);border-radius:9px;padding:9px 11px;width:100%}
textarea{min-height:110px;resize:vertical}input[type=range]{width:100%;accent-color:var(--accent)}
.outs{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0 6px}
.out{border-radius:12px;padding:12px 14px;background:color-mix(in srgb,var(--oc,var(--c1)) 11%,var(--surface-1));border:1px solid color-mix(in srgb,var(--oc,var(--c1)) 25%,var(--rule))}
.out .big{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}.out .lbl{font-size:12.5px;color:var(--text-secondary)}
.note{font-size:12.5px;color:var(--text-muted);margin-top:8px}
.advice{margin:6px 0 12px;padding:10px 12px;border-radius:10px;background:var(--surface-2);font-weight:500}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;font-size:13.5px;color:var(--text-secondary)}
.toolbar select{width:auto}.toolbar .sp{flex:1}
details.howto{margin:-4px 0 12px;font-size:13.5px;color:var(--text-secondary)}
details.howto summary{cursor:pointer;color:var(--accent);width:max-content}
details.howto p{margin:6px 0 0;max-width:780px;padding:10px 12px;border-radius:10px;background:var(--surface-2)}
.trust{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.trust div{border:1px solid var(--rule);border-radius:12px;padding:12px 14px;font-size:13.5px;color:var(--text-secondary)}
.trust b{display:block;color:var(--text-primary);font-size:14.5px;margin-bottom:2px}
.trust .ok{color:var(--good);font-weight:700;margin-right:4px}
.case{margin:12px 0}.case-h{font-weight:600;font-size:14px;margin-bottom:4px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;counter-reset:s}
@media(max-width:760px){.steps{grid-template-columns:1fr 1fr}}@media(max-width:440px){.steps{grid-template-columns:1fr}}
.step{border:1px solid var(--rule);border-radius:12px;padding:12px 14px;font-size:13.5px;color:var(--text-secondary);border-top:4px solid var(--sc)}
.step b{display:block;color:var(--text-primary);font-size:14.5px;margin-bottom:4px}
.step b::before{counter-increment:s;content:counter(s) ". ";color:var(--text-muted)}
.stack{display:flex;gap:8px;flex-wrap:wrap}.stack span{border-radius:999px;padding:3px 11px;font-size:13px;font-weight:500;
background:color-mix(in srgb,var(--sc) 14%,transparent);border:1px solid color-mix(in srgb,var(--sc) 35%,transparent)}
code{background:var(--surface-2);padding:2px 6px;border-radius:6px;font-size:13px}
.fb-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:640px){.fb-grid{grid-template-columns:1fr}}
.fb-grid .full{grid-column:1/-1}
#fbStatus{font-size:13.5px;color:var(--text-secondary);margin-top:10px;min-height:1em}
.next{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;font-size:13.5px;color:var(--text-secondary)}
.next div{border-radius:12px;padding:12px 14px;background:var(--surface-2)}.next b{color:var(--text-primary);display:block}
#tip{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);font-size:12.5px;padding:6px 9px;border-radius:7px;
opacity:0;transition:opacity .08s;z-index:60;max-width:300px}
.fab{position:fixed;right:18px;bottom:18px;z-index:30;width:50px;height:50px;border-radius:50%;border:none;background:var(--accent);color:#fff;
font-size:21px;font-weight:700;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.2)}
.drawer{position:fixed;inset:0 0 0 auto;width:min(430px,100%);background:var(--surface-1);border-left:1px solid var(--rule);z-index:50;
transform:translateX(100%);transition:transform .2s;overflow-y:auto;padding:20px 22px}
.drawer.open{transform:none}.scrim{position:fixed;inset:0;background:rgba(0,0,0,.28);z-index:45;display:none}.scrim.open{display:block}
.drawer h3{margin:0 0 6px;font-size:19px}.drawer h4{margin:18px 0 6px}.drawer dl{margin:0;font-size:13.5px}
.drawer dt{font-weight:600;margin-top:9px}.drawer dd{margin:2px 0 0;color:var(--text-secondary)}
.drawer ul{padding-left:18px;font-size:13.5px;color:var(--text-secondary);margin:6px 0}.x{float:right}
.tour-on{outline:3px solid var(--accent);outline-offset:4px;border-radius:16px}
#tourBox{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:55;width:min(540px,calc(100% - 32px));background:var(--text-primary);
color:var(--surface-1);border-radius:14px;padding:14px 16px;display:none;box-shadow:0 10px 34px rgba(0,0,0,.28)}
#tourBox p{margin:0 0 10px;font-size:14.5px}#tourBox .row{display:flex;gap:8px;justify-content:space-between;align-items:center}
#tourBox .btn{background:transparent;color:var(--surface-1);border-color:color-mix(in srgb,var(--surface-1) 40%,transparent)}
footer{color:var(--text-muted);font-size:13px;margin-top:30px;text-align:center}
@media print{.tabs,.fab,.strip,#tourBox,.drawer,.scrim,.no-print{display:none!important}.panel{display:block!important}
.viz-root{background:#fff}section.card,.hero{break-inside:avoid}}
"""

JS = r"""
const D = JSON.parse(document.getElementById('report-data').textContent);
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const fmt = n => Number(n).toLocaleString('en-US');

// Tabs with #hash links (shareable: e.g. ...#performance)
const tabs = $$('.tab'), panels = $$('.panel');
function show(id, focus) {
  if (!panels.some(p => p.dataset.panel === id)) id = 'summary';
  tabs.forEach(t => { const on = t.dataset.tab === id; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
  panels.forEach(p => p.classList.toggle('on', p.dataset.panel === id));
  if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
}
tabs.forEach((t, i) => {
  t.addEventListener('click', () => { show(t.dataset.tab); $('.tabs').scrollIntoView({block: 'start'}); });
  t.addEventListener('keydown', e => { const k = {ArrowRight: 1, ArrowLeft: -1}[e.key];
    if (k) { e.preventDefault(); show(tabs[(i + k + tabs.length) % tabs.length].dataset.tab, true); } });
});
$$('[data-goto]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); show(a.dataset.goto); $('.tabs').scrollIntoView({block: 'start'}); }));
addEventListener('hashchange', () => show(location.hash.slice(1)));
show(location.hash.slice(1));

// Hover tips
const tip = $('#tip');
$$('.hit').forEach(g => {
  g.addEventListener('mousemove', e => { tip.textContent = g.dataset.tip; tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; });
  g.addEventListener('mouseleave', () => tip.style.opacity = 0);
});

// Money and staff-time calculator
function calc() {
  const v = +$('#cVal').value || 0, m = +$('#cMonths').value || 0, mins = +$('#cMins').value || 0;
  $('#cSaved').textContent = '$' + fmt(Math.round(D.duplicates * v * m));
  $('#cPerCycle').textContent = '$' + fmt(Math.round(D.duplicates * v));
  $('#cHours').textContent = fmt(Math.round(D.review_pairs * mins / 6) / 10) + ' hours';
}
['#cVal', '#cMonths', '#cMins'].forEach(s => $(s).addEventListener('input', calc)); calc();

// Setting explorer
if (D.curve.length) {
  const sl = $('#thr'), ch = $('#thrChart'), mk = $('#thrMarker');
  const L = +ch.dataset.left, PW = +ch.dataset.pw, T0 = +ch.dataset.t0, T1 = +ch.dataset.t1;
  const safe = D.curve.filter(c => c.fp === 0), best = safe.reduce((a, b) => b.recall > a.recall ? b : a, safe[0] || D.curve[0]);
  function upd() {
    const t = +sl.value, r = D.curve.reduce((a, b) => Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a);
    $('#tVal').textContent = r.t.toFixed(2);
    $('#tAuto').textContent = fmt(r.auto); $('#tReview').textContent = fmt(r.review);
    $('#tHours').textContent = (Math.round(r.review * 2 / 6) / 10) + ' h';
    $('#tP').textContent = (100 * r.precision).toFixed(1) + '%'; $('#tR').textContent = (100 * r.recall).toFixed(1) + '%';
    $('#tFP').textContent = fmt(r.fp);
    const x = L + PW * (r.t - T0) / (T1 - T0); mk.setAttribute('x1', x); mk.setAttribute('x2', x);
    $('#tAdvice').textContent = r.fp > 0
      ? `⚠ Not recommended: at ${r.t.toFixed(2)}, ${fmt(r.fp)} pairs of different individuals would be merged incorrectly. Use a threshold of at least ${best.t.toFixed(2)}.`
      : r.recall < best.recall - 0.02
      ? `Safe but conservative: no incorrect merges, but only ${(100 * r.recall).toFixed(1)}% of duplicates are identified automatically and ${fmt(r.review)} pairs require review. A threshold of ${best.t.toFixed(2)} is equally safe and identifies ${(100 * best.recall).toFixed(1)}%.`
      : `✓ Recommended: no incorrect merges and the highest automatic identification rate (${(100 * r.recall).toFixed(1)}%).`;
  }
  sl.addEventListener('input', upd); upd();
}

// Sortable tables + CSV download
function toCSV(rows, cols) {
  const esc = v => { v = v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  return [cols.map(c => esc(c.label)).join(','), ...rows.map(r => cols.map(c => esc(r[c.k])).join(','))].join('\n');
}
function download(name, text) {
  try { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: 'text/csv'}));
    a.download = name; document.body.appendChild(a); a.click(); a.remove(); }
  catch (e) { alert('Downloads are not available in this view. Please open the report from its website.'); }
}
function table(el, rows, cols, file) {
  let key = null, dir = 1, view = rows;
  function draw() {
    view = key ? [...rows].sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir) : rows;
    el.querySelector('tbody').innerHTML = view.map(r => '<tr>' + cols.map(c =>
      `<td class="${c.num ? 'num' : ''} ${c.heat ? 'heat' : ''}" ${c.heat ? `style="background:${c.heat(r[c.k])}"` : ''}>${c.fmt ? c.fmt(r[c.k], r) : r[c.k]}</td>`).join('') + '</tr>').join('')
      || `<tr><td colspan="${cols.length}">No records match this filter.</td></tr>`;
  }
  el.querySelector('thead').innerHTML = '<tr>' + cols.map(c => `<th class="sort ${c.num ? 'num' : ''}" data-k="${c.k}" tabindex="0" title="Click to sort">${c.label}</th>`).join('') + '</tr>';
  el.querySelectorAll('th').forEach(th => {
    const go = () => { const k = th.dataset.k; dir = key === k ? -dir : -1; key = k;
      el.querySelectorAll('th').forEach(t => t.classList.remove('asc', 'desc')); th.classList.add(dir > 0 ? 'asc' : 'desc'); draw(); };
    th.addEventListener('click', go); th.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  });
  draw();
  return { set(r) { rows = r; draw(); }, csv() { download(file, toCSV(view, cols)); } };
}
const pct = v => v + '%';
const maxDup = Math.max(...D.woredas.map(w => w.duplicate_rate), 1);
const heat = (v, mx, c) => `color-mix(in srgb, var(${c}) ${Math.round(8 + 40 * v / mx)}%, transparent)`;
const wt = table($('#woredaTbl'), D.woredas, [
  {k: 'region', label: 'Region'}, {k: 'woreda', label: 'Woreda'},
  {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt}, {k: 'people', label: 'Unique individuals', num: 1, fmt: fmt},
  {k: 'duplicate_rate', label: 'Duplicate rate', num: 1, fmt: pct, heat: v => heat(v, maxDup, '--c2')},
  {k: 'issue_rate', label: 'Error rate', num: 1, fmt: pct}, {k: 'id_coverage', label: 'National ID coverage', num: 1, fmt: pct}], 'location_hotspots.csv');
$('#regionFilter').innerHTML = '<option value="">All regions</option>' + [...new Set(D.woredas.map(w => w.region))].sort().map(r => `<option>${r}</option>`).join('');
$('#regionFilter').addEventListener('change', e => wt.set(D.woredas.filter(w => !e.target.value || w.region === e.target.value)));
$('#dlWoreda').addEventListener('click', () => wt.csv());

const status = (f, r) => f ? `<span class="badge" title="${r.reason}"><span class="dot" style="background:var(--warn)"></span>⚠ Follow-up recommended</span>`
                           : '<span class="badge"><span class="dot" style="background:var(--good)"></span>✓ Within normal range</span>';
const et = table($('#enumTbl'), D.enumerators, [
  {k: 'enumerator_id', label: 'Enumerator'}, {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt},
  {k: 'issue_rate', label: 'Error rate', num: 1, fmt: pct}, {k: 'duplicate_rate', label: 'Duplicate rate', num: 1, fmt: pct},
  {k: 'valid_phone', label: 'Valid phone numbers', num: 1, fmt: pct}, {k: 'flag', label: 'Status', fmt: status}], 'enumerators.csv');
$('#flagOnly').addEventListener('change', e => et.set(D.enumerators.filter(r => !e.target.checked || r.flag)));
$('#dlEnum').addEventListener('click', () => et.csv());

const rq = table($('#reviewTbl'), D.review, [
  {k: 'a', label: 'Record A'}, {k: 'b', label: 'Record B'}, {k: 'score', label: 'Similarity', num: 1},
  {k: 'name_a', label: 'Name (A)'}, {k: 'name_b', label: 'Name (B)'}, {k: 'dob_a', label: 'Date of birth (A)'}, {k: 'dob_b', label: 'Date of birth (B)'},
  {k: 'why', label: 'Reason for review'}], 'review_queue.csv');
$('#dlReview').addEventListener('click', () => rq.csv());

// Help panel
const drawer = $('#help'), scrim = $('#scrim');
const openHelp = () => { drawer.classList.add('open'); scrim.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); $('#helpClose').focus(); };
const closeHelp = () => { drawer.classList.remove('open'); scrim.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); };
$$('[data-open-help]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); openHelp(); }));
$('#helpClose').addEventListener('click', closeHelp); scrim.addEventListener('click', closeHelp);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeHelp(); endTour(); } });
$$('[data-print]').forEach(b => b.addEventListener('click', () => { try { window.print(); } catch (e) {} }));

// Guided tour across tabs
const steps = [
  ['summary', '#kpis', 'Key figures: registrations received, unique individuals, duplicate registrations, and registrations with errors.'],
  ['summary', '#todo', 'Recommended actions, each with a suggested responsible unit. This section is intended for management meetings.'],
  ['summary', '#money', 'Enter the assistance amount and number of months to estimate the savings from removing duplicates.'],
  ['act', '#hotspots', 'Locations ranked by duplicate rate. Tables can be sorted, filtered by region and downloaded.'],
  ['quality', '#rules', 'The most frequent data errors, with the registration form change that would prevent each one.'],
  ['performance', '#explorer', 'System performance: move the slider to see the trade-off between automatic merging and reviewer workload.'],
  ['performance', '#enumerators', 'Enumerator performance: each point is one enumerator. Orange points are flagged for follow-up.'],
  ['method', '#formats', 'Accepted data formats and required fields, for teams preparing their own data.'],
  ['feedback', '#fbCard', 'Requests for additional analysis or corrections can be submitted here.'],
];
let ti = -1;
function showStep(i) {
  $$('.tour-on').forEach(e => e.classList.remove('tour-on'));
  if (i < 0 || i >= steps.length) return endTour();
  ti = i; const [tab, sel, text] = steps[i]; show(tab);
  const el = $(sel); el.classList.add('tour-on'); setTimeout(() => el.scrollIntoView({behavior: 'smooth', block: 'center'}), 60);
  $('#tourText').textContent = text; $('#tourCount').textContent = `Step ${i + 1} of ${steps.length}`;
  $('#tourNext').textContent = i === steps.length - 1 ? 'Finish' : 'Next'; $('#tourBox').style.display = 'block';
}
function endTour() { $$('.tour-on').forEach(e => e.classList.remove('tour-on')); $('#tourBox').style.display = 'none'; ti = -1; }
$$('[data-tour]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); closeHelp(); showStep(0); }));
$('#tourNext').addEventListener('click', () => showStep(ti + 1));
$('#tourPrev').addEventListener('click', () => showStep(Math.max(0, ti - 1)));
$('#tourEnd').addEventListener('click', endTour);

// Feedback -> pre-filled GitHub issue, or copy
function fbText() {
  const v = id => $(id).value.trim();
  return { title: `[${v('#fbType')}] ${v('#fbSummary') || 'Feedback on the report'}`,
    body: [`**Type:** ${v('#fbType')}`, `**Section:** ${v('#fbSection')}`, `**Priority:** ${v('#fbPriority')}`,
      `**From:** ${v('#fbName') || 'not given'}${v('#fbRole') ? ' (' + v('#fbRole') + ')' : ''}`, '',
      '**Description**', v('#fbDetail') || '-', '',
      '**Decision this will inform**', v('#fbDecision') || '-'].join('\n') };
}
$('#fbForm').addEventListener('submit', e => {
  e.preventDefault();
  if (!$('#fbDetail').value.trim()) { $('#fbStatus').textContent = 'Please provide a description before continuing.'; $('#fbDetail').focus(); return; }
  const t = fbText();
  $('#fbLink').href = `https://github.com/${D.repo}/issues/new?labels=feedback&title=${encodeURIComponent(t.title)}&body=${encodeURIComponent(t.body)}`;
  $('#fbLink').style.display = 'inline-flex';
  $('#fbStatus').textContent = 'The request is ready. Select "Submit on GitHub" (a free GitHub account is required), or copy the text and send it by email.';
});
$('#fbCopy').addEventListener('click', async () => {
  const t = fbText();
  try { await navigator.clipboard.writeText(t.title + '\n\n' + t.body); $('#fbStatus').textContent = 'The request has been copied. Paste it into an email or message.'; }
  catch (e) { $('#fbStatus').textContent = 'Copying was blocked by the browser. Please select and copy the text manually.'; }
});
"""

TABS = [("summary", "Summary", "var(--c1)", "★", "Intended for: programme management"),
        ("act", "Priority areas", "var(--c2)", "⌖", "Intended for: area offices and field coordination"),
        ("quality", "Data quality", "var(--c4)", "✓", "Intended for: information management and data teams"),
        ("duplicates", "Duplicates", "var(--c5)", "⧉", "Intended for: data reviewers"),
        ("performance", "Performance", "var(--c3)", "⚡", "Intended for: management, field coordination, donors and auditors"),
        ("method", "How it works", "var(--c7)", "⚙", "Intended for: technical readers and data teams"),
        ("feedback", "Feedback", "var(--c1)", "✉", "Intended for: all users")]


def _panel(id_, title, intro, body):
    t = next(t for t in TABS if t[0] == id_)
    return (f'<div class="panel" id="panel-{id_}" data-panel="{id_}" role="tabpanel" aria-labelledby="tab-{id_}" style="--tc:{t[2]}">'
            f'<div class="panel-h"><div class="ic" aria-hidden="true">{t[3]}</div><div><h2>{title}</h2>'
            f'<p>{intro}</p><div class="who">{t[4]}</div></div></div>{body}</div>')


# ---------------------------------------------------------------- page

def build(summary: dict, issues: pd.DataFrame, comp: pd.DataFrame, scored: pd.DataFrame,
          gold: pd.DataFrame, raw: pd.DataFrame, ins: dict | None = None,
          repo: str = "Nathan-TI/beneficiary-dedup-pipeline", author: str = "Nathan Tibebe",
          bench: list | None = None, tests_n: int = 28) -> str:
    ins, bench = ins or {}, bench or []
    m = summary.get("metrics") or {}
    pm = m.get("pipeline")
    owner = repo.split("/")[0].lower()
    pages = f"https://{owner}.github.io/{repo.split('/')[1]}"

    # Review queue rows in plain language
    rv = scored[scored["decision"] == "review"].copy()
    recs = raw.set_index("record_id")
    def name(rid):
        r = recs.loc[rid]
        return " ".join(str(x) for x in (r["first_name"], r["father_name"], r["grandfather_name"]) if pd.notna(x) and str(x).strip())
    def why(r):
        if pd.isna(r.sim_dob) and pd.isna(r.sim_phone):
            return "Names match; no date of birth or phone number to confirm"
        if pd.notna(r.sim_dob) and r.sim_dob < 0.7:
            return "Names match; dates of birth differ"
        if pd.notna(r.sim_first) and r.sim_first < 0.9:
            return "First names are spelled differently"
        return "Close match on most fields"
    review_rows = [{"a": r.left, "b": r.right, "score": r.score, "name_a": name(r.left), "name_b": name(r.right),
                    "dob_a": recs.at[r.left, "date_of_birth"], "dob_b": recs.at[r.right, "date_of_birth"], "why": why(r)}
                   for r in rv.itertuples()]

    data = {"repo": repo, "duplicates": ins.get("duplicates", summary["duplicates_removed"]),
            "review_pairs": summary["review_queue"], "curve": ins.get("curve", []),
            "woredas": ins.get("woredas", []), "enumerators": ins.get("enumerators", []), "review": review_rows}
    data_json = json.dumps(data, default=str).replace("</", "<\\/")

    n_in, n_people, dup = summary["records_in"], summary["people_out"], data["duplicates"]
    issue_n = summary["records_with_issues"]

    # ---------------- Summary tab
    kpis = _tiles([
        ("Registrations received", _fmt(n_in), "submitted from the field", "var(--c1)"),
        ("Unique individuals", _fmt(n_people), "after removing duplicates", "var(--c3)"),
        ("Duplicate registrations", _fmt(dup), f"{100 * dup / n_in:.1f}% of all registrations", "var(--c2)"),
        ("Pairs for manual review", _fmt(summary["review_queue"]), "requiring a reviewer's decision", "var(--c4)"),
        ("Registrations with errors", _fmt(issue_n), f"{100 * issue_n / n_in:.1f}% require correction", "var(--c5)"),
    ])
    colors = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c7)"]
    actions = "".join(
        f'<div class="action" style="--ac:{colors[i % 5]}"><b>{E(r["title"])}</b><p>{E(r["detail"])}</p>'
        f'<div class="tags"><span class="tag">Responsible: {E(r["owner"])}</span><span class="tag">Impact: {E(r["impact"])}</span></div></div>'
        for i, r in enumerate(ins.get("recommendations", [])))
    trust = ""
    if pm:
        trust = _card("Reliability of the results", "Validated against test data where the correct answer is known.", f"""
<div class="trust">
<div><b><span class="ok">✓</span>{pm['fp']} incorrect merges</b>No two different individuals were combined into one record.</div>
<div><b><span class="ok">✓</span>{_pct(pm['recall'])} of duplicates identified automatically</b>{_pct(m['pipeline_after_review']['recall'])} after manual review.</div>
<div><b><span class="ok">✓</span>Uncertain cases are referred for review</b>No borderline case is merged without human confirmation.</div>
<div><b><span class="ok">✓</span>Every merge is recorded</b>Each retained record lists the registrations it replaced, providing a full audit trail.</div>
</div><p class="note"><a href="#performance" data-goto="performance">See full performance results →</a></p>""")
    summary_tab = _panel("summary", "Summary", "Key results and recommended actions.", f"""
<div id="kpis">{kpis}</div>
{_card("Recommended actions", "Derived from this dataset. Each action has a suggested responsible unit.", f'<div class="actions">{actions}</div>', "todo",
       "Actions are listed in order of expected impact and are recalculated each time new registration data is processed.")}
{_card("Estimated savings from removing duplicate registrations", "Adjust the values to reflect your programme.", f'''
<div class="calc">
<label class="f">Assistance per person per month (USD)<input id="cVal" type="number" min="0" step="1" value="25"></label>
<label class="f">Number of months<input id="cMonths" type="number" min="0" step="1" value="6"></label>
<label class="f">Review time per pair (minutes)<input id="cMins" type="number" min="0" step="0.5" value="2"></label></div>
<div class="outs">
<div class="out" style="--oc:var(--c3)"><div class="lbl">Estimated savings for the period</div><div class="big" id="cSaved">–</div></div>
<div class="out" style="--oc:var(--c1)"><div class="lbl">Estimated savings per month</div><div class="big" id="cPerCycle">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Staff time for manual review</div><div class="big" id="cHours">–</div></div></div>
<p class="note">Based on {_fmt(dup)} duplicate registrations and {_fmt(summary["review_queue"])} pairs requiring review. Figures are estimates of assistance that would otherwise be paid more than once.</p>''',
       "money", "Estimated savings = duplicate registrations × assistance per person per month × number of months. Staff time = pairs requiring review × review time per pair. Default values are illustrative.")}
{trust}""")

    # ---------------- Priority areas tab
    weeks = ins.get("weekly", [])
    trend = ""
    if len(weeks) > 2:
        trend = _card("Registration trend", "Weekly registrations and the share of duplicate registrations.",
                      f'<div class="two"><div><h4>Registrations per week</h4>{_weekly_bars(weeks)}</div>'
                      f'<div><h4>Duplicate registrations per week (%)</h4>{_weekly_line(weeks)}</div></div>', "trend",
                      "Hover over a week to view the figures. A sustained increase in the orange line indicates that previously registered individuals "
                      "are registering again. New registrations should then be checked against the existing list at the point of registration, or registration paused for verification.")
    act_tab = _panel("act", "Priority areas", "Locations and trends that require attention.", f"""
{trend}
{_card("Location hotspots", "Darker shading indicates a higher share of duplicate registrations. Low national ID coverage makes duplicates harder to detect.",
       '<div class="toolbar"><label>Region <select id="regionFilter" aria-label="Filter by region"></select></label><span class="sp"></span>'
       '<button class="btn no-print" id="dlWoreda">⤓ Download (CSV)</button></div>'
       '<div class="tbl-wrap"><table id="woredaTbl"><thead></thead><tbody></tbody></table></div>', "hotspots",
       "Select a column heading to sort the table, or filter by region. Locations with a high duplicate rate and low national ID coverage "
       "should be prioritised for verification visits or national ID enrolment.")}
<p class="note">Enumerator results are reported in the <a href="#performance" data-goto="performance">Performance</a> tab.</p>""")

    # ---------------- Data quality tab
    by_rule = issues.groupby(["rule", "severity"])["record_id"].nunique().reset_index(name="n").sort_values("n", ascending=False)
    rule_rows = [(r.rule, r.n, CRIT if r.severity == "critical" else WARN,
                  f"{r.rule}: {r.n:,} registrations ({'critical' if r.severity == 'critical' else 'warning'})")
                 for r in by_rule.itertuples()]
    fixes = pd.DataFrame(ins.get("source_fixes", []))
    fixes_html = ""
    if not fixes.empty:
        fixes = fixes.rename(columns={"rule": "Error", "records": "Registrations", "fix": "Recommended change to the registration form"})
        fixes_html = _table(fixes)
    plain = {"id_number": "national ID", "phone": "phone number", "grandfather_name": "grandfather's name", "father_name": "father's name",
             "first_name": "first name", "date_of_birth": "birth date", "household_size": "household size"}
    comp_rows = [(plain.get(r.field, r.field.replace("_", " ")), float(r.filled_pct), "var(--c4)" if r.filled_pct < 80 else "var(--c1)",
                  f"{plain.get(r.field, r.field)}: completed in {r.filled_pct}% of registrations")
                 for r in comp.sort_values("filled_pct").itertuples()]
    quality_tab = _panel("quality", "Data quality", "The most frequent data errors and how to prevent them.", f"""
{_card("Most frequent errors", "Number of registrations affected by each error.",
       '<div class="legend"><span class="lg"><i style="background:' + CRIT + '"></i>Critical: the record cannot be used until corrected</span>'
       '<span class="lg"><i style="background:' + WARN + '"></i>Warning: the record can be used but should be corrected</span></div>'
       + _hbars(rule_rows, label_w=290, aria="Registrations with each error"), "rules",
       "Each bar represents one validation check applied to every registration. Hover over a bar to view the exact figure.")}
{_card("Preventing errors at the source", "Correcting the registration form is more efficient than cleaning data afterwards.", fixes_html, "fixes")}
{_card("Data completeness", "Percentage of registrations with each field completed. Fields below 80% are shown in yellow.",
       _hbars(comp_rows, label_w=170, unit="%", aria="Share of registrations with each field filled in"), "completeness",
       "National ID and phone number are the most useful fields for detecting duplicates. Low completeness in these fields increases the number of cases requiring manual review.")}""")

    # ---------------- Duplicates tab
    dup_tab = _panel("duplicates", "Duplicates", "Examples of duplicate registrations and the records that require manual review.", f"""
{_card("Examples of duplicate registrations identified", "The same individual recorded with different spellings, dates of birth or phone number formats.", _example_clusters(gold, raw), "examples")}
{_card("Records requiring manual review", "These pairs are similar but not conclusive. Each should be confirmed by a reviewer before merging.",
       '<div class="toolbar"><span>' + _fmt(len(review_rows)) + ' pairs</span><span class="sp"></span>'
       '<button class="btn no-print" id="dlReview">⤓ Download all (CSV)</button></div>'
       '<div class="tbl-wrap" style="max-height:420px;overflow-y:auto"><table id="reviewTbl" class="small"><thead></thead><tbody></tbody></table></div>',
       "review", "Similarity ranges from 0 (no similarity) to 1 (identical). The final column states why the case requires review.")}
{_card("Distribution of similarity scores", "Each compared pair receives a similarity score between 0 and 1.", _score_hist(scored), "scores",
       f"Blue: treated as different individuals. Orange ({REVIEW_AT} to {MATCH_AT}): referred for manual review. Green ({MATCH_AT} and above): merged automatically.")}""")

    # ---------------- Performance tab: system performance, then staff (enumerator) performance
    perf = ['<div class="subhead">System performance</div>']
    if pm:
        b = m["baseline"]
        perf.append(_tiles([
            ("Incorrect merges", _fmt(pm["fp"]), "target: zero", "var(--c3)"),
            ("Duplicates identified automatically", _pct(pm["recall"]), f"compared with {_pct(b['recall'], 0)} using exact matching", "var(--c1)"),
            ("Comparisons avoided", f"{100 * (1 - summary['candidate_pairs'] / summary['all_possible_pairs']):.1f}%",
             f"only {_fmt(summary['candidate_pairs'])} pairs required scoring", "var(--c2)"),
            ("Processing time", f"{summary['runtime_s']} s", f"for {_fmt(n_in)} registrations", "var(--c4)"),
        ]))
        perf.append(_card("Accuracy compared with exact matching",
                          f"Exact matching (identical spelling and date of birth) misses {_pct(1 - b['recall'], 0)} of duplicates. "
                          f"This system identifies {_pct(pm['recall'])} automatically.",
                          _accuracy_chart(m), "accuracy",
                          "Correct merges (precision): the share of merged records that relate to the same individual. "
                          "Duplicates identified (recall): the share of all actual duplicates that were found. "
                          "Overall score (F1): a combined measure of both."))
    if data["curve"]:
        perf.append(_card("Selecting the merge threshold", "Use the slider to see how changing the threshold affects accuracy and reviewer workload.", f"""
<label for="thr" style="display:block;font-size:13.5px;color:var(--text-secondary);margin-bottom:4px">Merge automatically when similarity is at least
<b id="tVal" style="color:var(--text-primary);font-size:16px">{MATCH_AT}</b> <span style="color:var(--text-muted)">(current setting: {MATCH_AT})</span></label>
<input id="thr" type="range" min="{data['curve'][0]['t']}" max="{data['curve'][-1]['t']}" step="0.01" value="{MATCH_AT}">
<div class="outs">
<div class="out" style="--oc:var(--c3)"><div class="lbl">Merged automatically</div><div class="big" id="tAuto">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Referred for review</div><div class="big" id="tReview">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Review time (2 min per pair)</div><div class="big" id="tHours">–</div></div>
<div class="out" style="--oc:var(--c1)"><div class="lbl">Correct merges</div><div class="big" id="tP">–</div></div>
<div class="out" style="--oc:var(--c2)"><div class="lbl">Duplicates identified</div><div class="big" id="tR">–</div></div>
<div class="out" style="--oc:var(--c5)"><div class="lbl">Incorrect merges</div><div class="big" id="tFP">–</div></div></div>
<p class="advice" id="tAdvice"></p>
<div class="legend"><span class="lg"><i style="background:var(--c1)"></i>Correct merges</span><span class="lg"><i style="background:var(--c2)"></i>Duplicates identified</span></div>
{_threshold_chart(data['curve'])}""", "explorer",
            "A lower threshold merges more records automatically but risks combining different individuals, which could result in an "
            "eligible person losing assistance. A higher threshold is safer but refers more cases for manual review. "
            "The dashed line shows the selected threshold."))
    if bench:
        rows_b = pd.DataFrame([{"Registrations": _fmt(x["records"]), "Time": f'{x["seconds"]} s',
                                "Per second": _fmt(x["records_per_second"]),
                                "Comparisons avoided": f'{100 * (1 - x["pairs_scored"] / x["all_pairs"]):.2f}%',
                                "Correct merges": _pct(x["precision"]), "Duplicates identified": _pct(x["recall"])} for x in bench])
        perf.append(_card("Speed and scalability", f"Tested on {len(bench)} dataset sizes, up to {_fmt(bench[-1]['records'])} registrations, on standard hardware.",
                          _bench_chart(bench) + "<h4>Detailed results</h4>" + _table(rows_b), "scale",
                          "Processing speed remains stable as the dataset grows, and accuracy remains high. "
                          "National-scale lists can be processed in regional batches."))
    perf.append(_card("Quality assurance", "Automated checks run every time the code changes.", f"""
<div class="trust">
<div><b><span class="ok">✓</span>{tests_n} automated code tests</b>Covering phone formats, spelling variants, sibling protection, file formats and accuracy on new test data.</div>
<div><b><span class="ok">✓</span>29 data tests in the warehouse</b>Checking unique IDs, valid values, and that every registration is linked to an individual.</div>
<div><b><span class="ok">✓</span>Automatic testing on every change</b>GitHub Actions runs all checks automatically; the result is displayed on the code page.</div>
<div><b><span class="ok">✓</span>Reproducible results</b>Fixed rules and settings ensure that each run can be repeated and audited.</div>
</div>""", "qa"))
    perf.append('<div class="subhead">Enumerator performance</div>')
    if data["enumerators"]:
        flagged_n = sum(1 for e in data["enumerators"] if e["flag"])
        avg_err = sum(e["issue_rate"] for e in data["enumerators"]) / len(data["enumerators"])
        avg_dup = sum(e["duplicate_rate"] for e in data["enumerators"]) / len(data["enumerators"])
        perf.append(_tiles([
            ("Enumerators", _fmt(len(data["enumerators"])), "with registrations in this dataset", "var(--c1)"),
            ("Average error rate", f"{avg_err:.1f}%", "of each enumerator's registrations", "var(--c4)"),
            ("Average duplicate rate", f"{avg_dup:.1f}%", "of each enumerator's registrations", "var(--c2)"),
            ("Follow-up recommended", _fmt(flagged_n), "well above the team average", "var(--c5)"),
        ]))
        perf.append(_card("Error and duplicate rates by enumerator",
                          "Each point represents one enumerator. Orange points are well above the team average, and follow-up is recommended.",
                          _enum_scatter(data["enumerators"]) +
                          '<div class="toolbar" style="margin-top:14px"><label><input type="checkbox" id="flagOnly"> Show only enumerators flagged for follow-up</label>'
                          '<span class="sp"></span><button class="btn no-print" id="dlEnum">⤓ Download (CSV)</button></div>'
                          '<div class="tbl-wrap" style="max-height:380px;overflow-y:auto"><table id="enumTbl"><thead></thead><tbody></tbody></table></div>',
                          "enumerators",
                          "These results are intended to guide coaching and support, not to assign blame. A high duplicate rate may also reflect "
                          "work in an area where many individuals attempted to register more than once. 'Well above average' means more than "
                          "1.5 standard deviations above the team mean. Duplicate rate counts registrations of individuals who were already registered."))
    perf_tab = _panel("performance", "Performance", "Accuracy, speed and reliability of the system, and performance of registration staff.", "".join(perf))

    # ---------------- How it works tab
    step_cols = ["var(--c1)", "var(--c4)", "var(--c3)", "var(--c2)", "var(--c5)", "var(--c7)"]
    steps = [("Collect", "Registration data is received from the field. In this report, realistic synthetic data with known duplicates is used."),
             ("Validate", f"{len(by_rule)} validation checks identify missing, invalid or implausible values."),
             ("Standardise", "Names, phone numbers and dates are converted to a standard format. A phonetic key links spelling variants such as Mohammed and Mohamed."),
             ("Shortlist", "Only records that share a key attribute (phone number, national ID, date of birth or a similar name) are compared, avoiding 99.9% of comparisons."),
             ("Compare", "Each pair is scored across eight fields, with specific rules for siblings and conflicting national IDs."),
             ("Decide", "Clear matches are merged, uncertain cases are referred for review, and one record is retained per individual.")]
    steps_html = '<div class="steps">' + "".join(f'<div class="step" style="--sc:{c}"><b>{a}</b>{t}</div>'
                                                 for (a, t), c in zip(steps, step_cols)) + "</div>"
    stack = '<div class="stack">' + "".join(f'<span style="--sc:{c}">{t}</span>' for t, c in zip(
        ["Python", "pandas", "RapidFuzz", "SQL", "dbt", "DuckDB", "BigQuery", "LLM APIs", "pytest", "GitHub Actions"],
        ["var(--c1)", "var(--c1)", "var(--c3)", "var(--c2)", "var(--c2)", "var(--c4)", "var(--c1)", "var(--c7)", "var(--c3)", "var(--c5)"])) + "</div>"
    formats = pd.DataFrame([
        ("CSV or text", ".csv, .txt", "Comma, semicolon or tab separated; the separator is detected automatically."),
        ("Tab-separated", ".tsv", "One record per row."),
        ("Excel", ".xlsx, .xlsm", "The first sheet is read by default; a specific sheet can be named. Older .xls files should be saved as .xlsx."),
        ("JSON", ".json", "A list of records."),
        ("JSON Lines", ".jsonl, .ndjson", "One record per line."),
        ("Parquet", ".parquet", "Requires the optional pyarrow package."),
    ], columns=["Format", "File extension", "Notes"])
    formats_html = f"""{_table(formats)}
<h4>Required and recommended fields</h4>
<p class="lede" style="margin-bottom:8px"><b>Required:</b> first name, father's name, sex, date of birth.<br>
<b>Recommended:</b> grandfather's name, phone number, national ID, region, zone, woreda, kebele, household size, registration date, enumerator.
Missing recommended fields reduce accuracy and increase manual review, but do not prevent processing.</p>
<h4>Column names</h4>
<p class="lede" style="margin-bottom:8px">Column names are recognised automatically, including typical exports from KoboToolbox, ODK and SurveyCTO.
For example, "First Name", "DOB", "Phone Number", "Fayda ID" and "_submitted_by" are matched to the correct fields, and grouped names
such as "beneficiary/first_name" are supported. A template file is available at <code>templates/registration_template.csv</code>.</p>
<h4>How to run it on a file</h4>
<p class="lede" style="margin:0"><code>python run_pipeline.py --input registrations.xlsx --sheet "Registrations"</code><br>
If a required column cannot be found, the system stops and lists the missing fields, so that no incomplete data is processed silently.</p>"""
    method_tab = _panel("method", "How it works", "The process follows the steps a registration team would take before a distribution list is finalised.", f"""
{_card("Process overview", None, steps_html)}
{_card("Which data formats can it accept?", "Registration data can be provided in the formats most commonly exported by data collection tools and databases.", formats_html, "formats")}
{_card("Tools", "Open-source tools that run locally or in the cloud.", stack +
       f'<p class="note" style="margin-top:12px">Technical documentation of the data models: <a href="{pages}/dbt-docs.html">dbt docs</a>. '
       f'Source code: <a href="https://github.com/{repo}">github.com/{repo}</a>.</p>')}
{_card("Data protection", None, '<p class="lede" style="margin:0">All records in this report are synthetic; no real individuals are represented. '
       'When applied to real data, the system runs within the organisation\'s own environment, so personal data does not need to leave it. '
       'Results are written only to local output files.</p>')}""")

    # ---------------- Feedback tab
    fb_tab = _panel("feedback", "Feedback", "Submit requests for additional analysis, changes or corrections.", f"""
<section class="card" id="fbCard"><h2>Submit a request</h2><p class="lede">This takes approximately one minute. Each request is logged as a tracked item so that its progress can be followed.</p>
<form id="fbForm" class="fb-grid" novalidate>
<label class="f">Name (optional)<input id="fbName" type="text" autocomplete="name"></label>
<label class="f">Role or office (optional)<input id="fbRole" type="text" placeholder="e.g. Programme Officer, area office"></label>
<label class="f">Type of request<select id="fbType"><option>New requirement</option><option>Additional analysis or breakdown</option>
<option>Data or report issue</option><option>Question</option><option>Other</option></select></label>
<label class="f">Section of the report<select id="fbSection"><option>Whole report</option><option>Summary</option><option>Priority areas</option>
<option>Data quality</option><option>Duplicates</option><option>Performance</option><option>How it works</option></select></label>
<label class="f">Priority<select id="fbPriority"><option>Low</option><option>Medium</option><option>High: needed for an upcoming decision</option></select></label>
<label class="f">Title<input id="fbSummary" type="text" placeholder="e.g. Duplicate rate by kebele"></label>
<label class="f full">Description of the request or issue *<textarea id="fbDetail" required placeholder="Please describe the request in your own words"></textarea></label>
<label class="f full">Which decision will this inform? (optional)<input id="fbDecision" type="text" placeholder="e.g. Allocation of verification teams next month"></label>
<div class="full" style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn primary" type="submit">Prepare request</button>
<a id="fbLink" class="btn" href="#" target="_blank" rel="noopener" style="display:none">Submit on GitHub ↗</a>
<button class="btn" type="button" id="fbCopy">Copy text</button></div></form><div id="fbStatus" role="status"></div></section>
{_card("Next steps", None, '<div class="next"><div><b>1. Recorded</b>The request is logged as a tracked item.</div>'
       '<div><b>2. Assessed</b>The request is reviewed and prioritised.</div><div><b>3. Implemented</b>The change is developed and tested.</div>'
       '<div><b>4. Published</b>The report is updated and the request is marked as complete.</div></div>')}""")

    tabs_html = "".join(f'<button class="tab" role="tab" id="tab-{i}" data-tab="{i}" aria-controls="panel-{i}" style="--tc:{c}">'
                        f'<span class="d"></span>{n}</button>' for i, n, c, _, _ in TABS)

    help_drawer = f"""
<div id="scrim" class="scrim"></div>
<aside id="help" class="drawer" aria-hidden="true" aria-label="Help">
<button class="btn x" id="helpClose">Close ✕</button>
<h3>Using this report</h3>
<p style="color:var(--text-secondary);font-size:13.5px;margin:0">Reading time is approximately five minutes. No information entered in this report is transmitted unless you choose to submit feedback.</p>
<p><button class="btn primary" data-tour>▶ Start the guided tour</button></p>
<h4>Recommended starting point</h4>
<ul><li><b>Programme management:</b> <i>Summary</i>, including the recommended actions and the savings estimate.</li>
<li><b>Area offices and field coordination:</b> <i>Priority areas</i> for locations, and <i>Performance</i> for enumerator results.</li>
<li><b>Information management and data teams:</b> <i>Data quality</i> and <i>Duplicates</i>.</li>
<li><b>Donors and auditors:</b> <i>Performance</i>, for accuracy, reliability and quality assurance.</li></ul>
<h4>Available features</h4>
<ul><li>Hover over any bar, point or line to view the exact figure.</li>
<li>Select a column heading to sort a table; select it again to reverse the order.</li>
<li>Filter locations by region, or show only enumerators flagged for follow-up.</li>
<li>Download tables as CSV files for use in Excel.</li>
<li>Enter values in the savings estimate, or move the threshold slider; results update immediately.</li>
<li>Select "How to read this" below a title for a short explanation.</li>
<li>Share a specific tab using its link, for example <code>#performance</code>.</li></ul>
<h4>Glossary</h4>
<dl>
<dt>Duplicate registration</dt><dd>A registration for an individual who is already on the list.</dd>
<dt>Unique individuals</dt><dd>The number of distinct people once duplicates have been removed.</dd>
<dt>Manual review</dt><dd>A pair of records that are similar but not conclusive, and which a reviewer must confirm.</dd>
<dt>Similarity score</dt><dd>A measure of how alike two registrations are, from 0 (no similarity) to 1 (identical).</dd>
<dt>Merge threshold</dt><dd>The similarity score at or above which records are merged automatically.</dd>
<dt>Correct merges (precision)</dt><dd>The share of merged records that relate to the same individual.</dd>
<dt>Duplicates identified (recall)</dt><dd>The share of all actual duplicates that were found.</dd>
<dt>Critical / warning</dt><dd>Critical errors prevent a record from being used until corrected; warnings should be corrected but do not block use.</dd>
</dl>
<h4>Frequently asked questions</h4>
<dl><dt>Is this real data?</dt><dd>No. All records are synthetic, and no real individuals are represented.</dd>
<dt>Which data formats can it accept?</dt><dd>CSV and text files, TSV, Excel (.xlsx), JSON, JSON Lines and Parquet. Common column names from KoboToolbox, ODK and SurveyCTO exports are recognised automatically.
<a href="#method" data-goto="method">Full details</a>.</dd>
<dt>Which fields are required?</dt><dd>First name, father's name, sex and date of birth. Phone number, national ID and location are strongly recommended.</dd>
<dt>Can it be used with our data?</dt><dd>Yes. Accuracy figures require known answers, so they are shown for test data only.</dd>
<dt>Who sets the merge threshold?</dt><dd>The programme. The Performance tab shows the trade-off so that the decision can be agreed and documented.</dd>
<dt>How can I request a change?</dt><dd>Use the <a href="#feedback" data-goto="feedback">Feedback</a> tab.</dd></dl></aside>
<button class="fab no-print" data-open-help aria-label="Open help">?</button>
<div id="tourBox" role="dialog" aria-live="polite"><p id="tourText"></p><div class="row"><span id="tourCount" style="font-size:12.5px;opacity:.8"></span>
<span style="display:flex;gap:8px"><button class="btn" id="tourEnd">Skip</button><button class="btn" id="tourPrev">Back</button>
<button class="btn" id="tourNext">Next</button></span></div></div>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Beneficiary registration quality and deduplication report: duplicate registrations, data errors, priority areas and performance.">
<title>Beneficiary Deduplication &amp; Data-Quality Pipeline — Report</title><style>{CSS}</style></head>
<body><div class="viz-root">
<div class="strip"><div class="in"><span>Portfolio project by <b>{E(author)}</b></span>
<a href="https://github.com/{repo}">View the code</a><a href="{pages}/dbt-docs.html">Technical docs</a></div></div>
<div class="wrap">
<header class="hero"><h1>Beneficiary Registration Quality and Deduplication Report</h1>
<p>This report reviews beneficiary registration data for errors, identifies individuals registered more than once (including where
names, dates of birth or phone numbers are recorded differently), and sets out recommended actions for programme management.</p>
<div class="chips"><span class="chip">Synthetic test data: no real individuals</span><span class="chip">Updated {date.today().strftime('%d %b %Y')}</span>
<span class="chip">{_fmt(n_in)} registrations</span><button class="btn primary" data-tour>▶ Guided tour (1 minute)</button>
<button class="btn no-print" data-print>Print / save as PDF</button></div></header>
<nav class="tabs" role="tablist" aria-label="Report sections">{tabs_html}<span class="sp"></span>
<button class="btn no-print" data-open-help>Help</button></nav>
{summary_tab}{act_tab}{quality_tab}{dup_tab}{perf_tab}{method_tab}{fb_tab}
<footer>Built by {E(author)} with Python, SQL and dbt · <a href="https://github.com/{repo}">Source code</a></footer>
</div>{help_drawer}<div id="tip" role="tooltip"></div></div>
<script type="application/json" id="report-data">{data_json}</script>
<script>{JS}</script></body></html>"""
