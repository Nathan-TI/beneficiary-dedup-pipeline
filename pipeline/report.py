"""Interactive, self-contained HTML report (no external assets) — works offline and on GitHub Pages.

Organised as tabs for different readers:
  Summary (managers) · Where to act (field/area teams) · Data quality (data teams) ·
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
              ("pipeline", "This system, automatic", "var(--c2)"),
              ("pipeline_after_review", "This system + quick human check", "var(--c3)")]
    groups = [("precision", "Correct merges"), ("recall", "Duplicates caught"), ("f1", "Overall score")]
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
                     ("checked by a person", "var(--c2)") if lo >= REVIEW_AT - 1e-9 else ("kept apart", "var(--c1)"))
        x = left + i * bw
        parts.append(f'<g class="hit" data-tip="Score {lo:.3f}–{hi:.3f}: {_fmt(c)} pairs ({zone})">'
                     f'<rect x="{x}" y="{top}" width="{bw}" height="{ph}" fill="transparent"/>'
                     f'<path d="{_col_path(x + 1, top + ph, bw - 2, ph * c / mx)}" fill="{col}"/></g>')
    for t in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<text x="{left + pw * t}" y="{H - 10}" text-anchor="middle" class="ax">{t:.2f}</text>')
    legend = ('<div class="legend"><span class="lg"><i style="background:var(--c1)"></i>Kept apart (different people)</span>'
              f'<span class="lg"><i style="background:var(--c2)"></i>Checked by a person ({REVIEW_AT}–{MATCH_AT})</span>'
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
    for key, col, name in (("precision", "var(--c1)", "Correct merges"), ("recall", "var(--c2)", "Duplicates caught")):
        pts = " ".join(f"{x(r['t']):.1f},{y(r[key]):.1f}" for r in curve)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>')
        parts.append(f'<text x="{x(curve[-1]["t"]) + 8}" y="{y(curve[-1][key]) + 4}" class="val">{name}</text>')
    parts.append(f'<line id="thrMarker" x1="{x(MATCH_AT)}" x2="{x(MATCH_AT)}" y1="{top}" y2="{top + ph}" class="thr"/>')
    return (f'<svg id="thrChart" data-left="{left}" data-pw="{pw}" data-t0="{t0}" data-t1="{t1}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="Correct merges and duplicates caught at each setting">{"".join(parts)}</svg>')


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
        parts.append(f'<g class="hit" data-tip="Week of {w["week"]}: {w["duplicate_rate"]}% were repeat registrations">'
                     f'<rect x="{a - step / 2}" y="{top}" width="{step}" height="{ph}" fill="transparent"/>'
                     f'<circle cx="{a}" cy="{b}" r="4" fill="var(--c2)" stroke="var(--surface-1)" stroke-width="2"/></g>')
    for i, w in enumerate(weeks):
        if i % 4 == 0:
            parts.append(f'<text x="{pts[i][0]}" y="{H - 10}" text-anchor="middle" class="ax">{w["week"][5:]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Repeat registrations per week">{"".join(parts)}</svg>'


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
    parts.append(f'<text x="{left + pw / 2}" y="{H - 2}" text-anchor="middle" class="ax">Share of registrations with errors →</text>')
    parts.append(f'<text transform="translate(12 {top + ph / 2}) rotate(-90)" text-anchor="middle" class="ax">Repeat registrations →</text>')
    placed = []
    for e in sorted(enums, key=lambda e: e["flag"]):
        x = left + pw * e["issue_rate"] / xm
        yy = top + ph * (1 - e["duplicate_rate"] / ym)
        col = "var(--c2)" if e["flag"] else "var(--c1)"
        tip = f'{e["enumerator_id"]}: {e["issue_rate"]}% with errors, {e["duplicate_rate"]}% repeat registrations' + (
            f' · needs coaching ({e["reason"]})' if e["flag"] else "")
        parts.append(f'<g class="hit" data-tip="{E(tip)}"><circle cx="{x}" cy="{yy}" r="12" fill="transparent"/>'
                     f'<circle cx="{x}" cy="{yy}" r="{6 if e["flag"] else 5}" fill="{col}" stroke="var(--surface-1)" stroke-width="2"/></g>')
        if e["flag"]:
            ly = yy - 8
            while any(abs(ly - py) < 14 and abs(x - px) < 70 for px, py in placed):
                ly += 15
            placed.append((x, ly))
            parts.append(f'<text x="{x + 10}" y="{ly}" class="val" style="font-size:11.5px;font-weight:600">{e["enumerator_id"]}</text>')
    legend = ('<div class="legend"><span class="lg"><i style="background:var(--c1);border-radius:50%"></i>Within normal range</span>'
              '<span class="lg"><i style="background:var(--c2);border-radius:50%"></i>Needs coaching</span></div>')
    return legend + f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Enumerators by error rate and repeat registrations">{"".join(parts)}</svg>'


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
            out.append(f'<div class="case"><div class="case-h">Person {len(out) + 1} · registered {len(sub)} times</div>'
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
      ? `⚠ Too loose: at ${r.t.toFixed(2)}, ${fmt(r.fp)} pairs of different people would be merged by mistake. Move the slider to at least ${best.t.toFixed(2)}.`
      : r.recall < best.recall - 0.02
      ? `Safe, but strict: no mistakes, but only ${(100 * r.recall).toFixed(1)}% of duplicates are caught automatically and ${fmt(r.review)} pairs need a person. ${best.t.toFixed(2)} is just as safe and catches ${(100 * best.recall).toFixed(1)}%.`
      : `✓ Best balance: no mistakes, and the most duplicates caught automatically (${(100 * r.recall).toFixed(1)}%).`;
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
  catch (e) { alert('Download is not available here. Open the report from its website to download.'); }
}
function table(el, rows, cols, file) {
  let key = null, dir = 1, view = rows;
  function draw() {
    view = key ? [...rows].sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir) : rows;
    el.querySelector('tbody').innerHTML = view.map(r => '<tr>' + cols.map(c =>
      `<td class="${c.num ? 'num' : ''} ${c.heat ? 'heat' : ''}" ${c.heat ? `style="background:${c.heat(r[c.k])}"` : ''}>${c.fmt ? c.fmt(r[c.k], r) : r[c.k]}</td>`).join('') + '</tr>').join('')
      || `<tr><td colspan="${cols.length}">Nothing matches this filter.</td></tr>`;
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
  {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt}, {k: 'people', label: 'Real people', num: 1, fmt: fmt},
  {k: 'duplicate_rate', label: 'Repeat registrations', num: 1, fmt: pct, heat: v => heat(v, maxDup, '--c2')},
  {k: 'issue_rate', label: 'With errors', num: 1, fmt: pct}, {k: 'id_coverage', label: 'Have national ID', num: 1, fmt: pct}], 'location_hotspots.csv');
$('#regionFilter').innerHTML = '<option value="">All regions</option>' + [...new Set(D.woredas.map(w => w.region))].sort().map(r => `<option>${r}</option>`).join('');
$('#regionFilter').addEventListener('change', e => wt.set(D.woredas.filter(w => !e.target.value || w.region === e.target.value)));
$('#dlWoreda').addEventListener('click', () => wt.csv());

const status = (f, r) => f ? `<span class="badge" title="${r.reason}"><span class="dot" style="background:var(--warn)"></span>⚠ Needs coaching</span>`
                           : '<span class="badge"><span class="dot" style="background:var(--good)"></span>✓ OK</span>';
const et = table($('#enumTbl'), D.enumerators, [
  {k: 'enumerator_id', label: 'Enumerator'}, {k: 'registrations', label: 'Registrations', num: 1, fmt: fmt},
  {k: 'issue_rate', label: 'With errors', num: 1, fmt: pct}, {k: 'duplicate_rate', label: 'Repeat registrations', num: 1, fmt: pct},
  {k: 'valid_phone', label: 'Valid phone', num: 1, fmt: pct}, {k: 'flag', label: 'Status', fmt: status}], 'enumerators.csv');
$('#flagOnly').addEventListener('change', e => et.set(D.enumerators.filter(r => !e.target.checked || r.flag)));
$('#dlEnum').addEventListener('click', () => et.csv());

const rq = table($('#reviewTbl'), D.review, [
  {k: 'a', label: 'Record A'}, {k: 'b', label: 'Record B'}, {k: 'score', label: 'Similarity', num: 1},
  {k: 'name_a', label: 'Name on A'}, {k: 'name_b', label: 'Name on B'}, {k: 'dob_a', label: 'Birth date A'}, {k: 'dob_b', label: 'Birth date B'},
  {k: 'why', label: 'Why it needs a person'}], 'review_queue.csv');
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
  ['summary', '#kpis', 'The headline: how many registrations came in, how many real people that is, and how many were repeats or had errors.'],
  ['summary', '#todo', 'Five actions for this week, each with a suggested owner. Start here in a management meeting.'],
  ['summary', '#money', 'Type in your own transfer amount and number of months to see what removing duplicates saves.'],
  ['act', '#hotspots', 'Where to act: locations sorted by repeat registrations. Sort any column, filter by region, or download the list.'],
  ['act', '#enumerators', 'Which enumerators need coaching. Each dot is one enumerator; orange dots are well above average.'],
  ['quality', '#rules', 'The most common data errors, and the change to the registration form that would stop each one.'],
  ['performance', '#explorer', 'Can we trust it? Drag the slider to see the trade-off between automatic merging and work for reviewers.'],
  ['feedback', '#fbCard', 'Need something else? Describe it here and it becomes a tracked request.'],
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
    body: [`**Type:** ${v('#fbType')}`, `**Part of the report:** ${v('#fbSection')}`, `**How urgent:** ${v('#fbPriority')}`,
      `**From:** ${v('#fbName') || 'not given'}${v('#fbRole') ? ' (' + v('#fbRole') + ')' : ''}`, '',
      '**What do you need, or what did you notice?**', v('#fbDetail') || '-', '',
      '**What decision would this help you make?**', v('#fbDecision') || '-'].join('\n') };
}
$('#fbForm').addEventListener('submit', e => {
  e.preventDefault();
  if (!$('#fbDetail').value.trim()) { $('#fbStatus').textContent = 'Please tell us what you need first.'; $('#fbDetail').focus(); return; }
  const t = fbText();
  $('#fbLink').href = `https://github.com/${D.repo}/issues/new?labels=feedback&title=${encodeURIComponent(t.title)}&body=${encodeURIComponent(t.body)}`;
  $('#fbLink').style.display = 'inline-flex';
  $('#fbStatus').textContent = 'Ready. Click "Send on GitHub" (needs a free GitHub account), or copy the text and email it.';
});
$('#fbCopy').addEventListener('click', async () => {
  const t = fbText();
  try { await navigator.clipboard.writeText(t.title + '\n\n' + t.body); $('#fbStatus').textContent = 'Copied. Paste it into an email or chat message.'; }
  catch (e) { $('#fbStatus').textContent = 'Your browser blocked copying. Select the text in the boxes and copy it yourself.'; }
});
"""

TABS = [("summary", "Summary", "var(--c1)", "★", "For managers"),
        ("act", "Where to act", "var(--c2)", "⌖", "For area offices and field coordinators"),
        ("quality", "Data quality", "var(--c4)", "✓", "For information management and data teams"),
        ("duplicates", "Duplicates", "var(--c5)", "⧉", "For reviewers"),
        ("performance", "Performance", "var(--c3)", "⚡", "For anyone who needs to trust the results"),
        ("method", "How it works", "var(--c7)", "⚙", "For technical readers"),
        ("feedback", "Feedback", "var(--c1)", "✉", "For everyone")]


def _panel(id_, title, intro, body):
    t = next(t for t in TABS if t[0] == id_)
    return (f'<div class="panel" id="panel-{id_}" data-panel="{id_}" role="tabpanel" aria-labelledby="tab-{id_}" style="--tc:{t[2]}">'
            f'<div class="panel-h"><div class="ic" aria-hidden="true">{t[3]}</div><div><h2>{title}</h2>'
            f'<p>{intro}</p><div class="who">{t[4]}</div></div></div>{body}</div>')


# ---------------------------------------------------------------- page

def build(summary: dict, issues: pd.DataFrame, comp: pd.DataFrame, scored: pd.DataFrame,
          gold: pd.DataFrame, raw: pd.DataFrame, ins: dict | None = None,
          repo: str = "Nathan-TI/beneficiary-dedup-pipeline", author: str = "Nathan Tibebe",
          bench: list | None = None) -> str:
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
            return "Names match but no birth date or phone to confirm"
        if pd.notna(r.sim_dob) and r.sim_dob < 0.7:
            return "Names match but birth dates differ"
        if pd.notna(r.sim_first) and r.sim_first < 0.9:
            return "First names are spelled differently"
        return "Close match on most details"
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
        ("Registrations received", _fmt(n_in), "from field registration", "var(--c1)"),
        ("Real people", _fmt(n_people), "after removing repeats", "var(--c3)"),
        ("Repeat registrations", _fmt(dup), f"{100 * dup / n_in:.1f}% of all registrations", "var(--c2)"),
        ("Pairs for a quick check", _fmt(summary["review_queue"]), "a person decides", "var(--c4)"),
        ("Registrations with errors", _fmt(issue_n), f"{100 * issue_n / n_in:.1f}% need fixing", "var(--c5)"),
    ])
    colors = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c7)"]
    actions = "".join(
        f'<div class="action" style="--ac:{colors[i % 5]}"><b>{E(r["title"])}</b><p>{E(r["detail"])}</p>'
        f'<div class="tags"><span class="tag">Who: {E(r["owner"])}</span><span class="tag">Impact: {E(r["impact"])}</span></div></div>'
        for i, r in enumerate(ins.get("recommendations", [])))
    trust = ""
    if pm:
        trust = _card("Can we trust these numbers?", "Tested against data where the right answer is known.", f"""
<div class="trust">
<div><b><span class="ok">✓</span>{pm['fp']} people merged by mistake</b>No real person was wrongly joined with someone else.</div>
<div><b><span class="ok">✓</span>{_pct(pm['recall'])} of repeats caught automatically</b>{_pct(m['pipeline_after_review']['recall'])} after the quick human check.</div>
<div><b><span class="ok">✓</span>Unclear cases go to a person</b>Nothing borderline is merged without someone checking it.</div>
<div><b><span class="ok">✓</span>Every merge is recorded</b>Each kept record lists the registrations it replaced, so decisions can be audited.</div>
</div><p class="note"><a href="#performance" data-goto="performance">See full performance results →</a></p>""")
    summary_tab = _panel("summary", "Summary", "What happened, what it means, and what to do next.", f"""
<div id="kpis">{kpis}</div>
{_card("What to do next", "Generated from this data. Each action has a suggested owner.", f'<div class="actions">{actions}</div>', "todo",
       "The actions are ordered by expected impact. They are recalculated every time new registration data is processed, so this list stays current.")}
{_card("Money saved by removing repeat registrations", "Change the numbers to match your programme.", f'''
<div class="calc">
<label class="f">Assistance per person per month (USD)<input id="cVal" type="number" min="0" step="1" value="25"></label>
<label class="f">Number of months<input id="cMonths" type="number" min="0" step="1" value="6"></label>
<label class="f">Minutes to check one pair<input id="cMins" type="number" min="0" step="0.5" value="2"></label></div>
<div class="outs">
<div class="out" style="--oc:var(--c3)"><div class="lbl">Saved over the whole period</div><div class="big" id="cSaved">–</div></div>
<div class="out" style="--oc:var(--c1)"><div class="lbl">Saved every month</div><div class="big" id="cPerCycle">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Staff time for quick checks</div><div class="big" id="cHours">–</div></div></div>
<p class="note">Based on {_fmt(dup)} repeat registrations and {_fmt(summary["review_queue"])} pairs to check. These are estimates of assistance that would otherwise be paid twice.</p>''',
       "money", "Money saved = repeat registrations × assistance per person per month × number of months. Staff time = pairs to check × minutes per pair. The starting values are examples.")}
{trust}""")

    # ---------------- Where to act tab
    weeks = ins.get("weekly", [])
    trend = ""
    if len(weeks) > 2:
        trend = _card("Registration trend", "How many people were registered each week, and how many of them were already on the list.",
                      f'<div class="two"><div><h4>Registrations per week</h4>{_weekly_bars(weeks)}</div>'
                      f'<div><h4>Repeat registrations per week</h4>{_weekly_line(weeks)}</div></div>', "trend",
                      "Hover over a week to see the numbers. If the orange line keeps rising, more people are coming back to register again. "
                      "That's a signal to check new registrations against the existing list on the spot, or to pause and verify.")
    act_tab = _panel("act", "Where to act", "Which locations and which enumerators need attention first.", f"""
{trend}
{_card("Location hotspots", "Darker orange means more repeat registrations. Low national ID coverage makes repeats harder to catch.",
       '<div class="toolbar"><label>Region <select id="regionFilter" aria-label="Filter by region"></select></label><span class="sp"></span>'
       '<button class="btn no-print" id="dlWoreda">⤓ Download list (CSV)</button></div>'
       '<div class="tbl-wrap"><table id="woredaTbl"><thead></thead><tbody></tbody></table></div>', "hotspots",
       "Click a column name to sort. Use the region filter to narrow the list. A location with many repeats and few national IDs "
       "is the best candidate for a verification visit or national ID enrolment.")}
{_card("Enumerator performance", "Each dot is one enumerator. Orange dots are well above the team average and may need coaching.",
       (_enum_scatter(data["enumerators"]) if data["enumerators"] else "") +
       '<div class="toolbar" style="margin-top:14px"><label><input type="checkbox" id="flagOnly"> Show only those who need coaching</label>'
       '<span class="sp"></span><button class="btn no-print" id="dlEnum">⤓ Download list (CSV)</button></div>'
       '<div class="tbl-wrap" style="max-height:380px;overflow-y:auto"><table id="enumTbl"><thead></thead><tbody></tbody></table></div>', "enumerators",
       "Use this to plan coaching, not to blame. A high repeat rate can also mean the enumerator worked where many people tried to "
       "register twice. 'Well above average' means more than 1.5 standard deviations above the team.")}""")

    # ---------------- Data quality tab
    by_rule = issues.groupby(["rule", "severity"])["record_id"].nunique().reset_index(name="n").sort_values("n", ascending=False)
    rule_rows = [(r.rule, r.n, CRIT if r.severity == "critical" else WARN,
                  f"{r.rule}: {r.n:,} registrations ({'must fix' if r.severity == 'critical' else 'should fix'})")
                 for r in by_rule.itertuples()]
    fixes = pd.DataFrame(ins.get("source_fixes", []))
    fixes_html = ""
    if not fixes.empty:
        fixes = fixes.rename(columns={"rule": "Problem", "records": "Registrations", "fix": "How to stop it in the registration form"})
        fixes_html = _table(fixes)
    plain = {"id_number": "national ID", "phone": "phone number", "grandfather_name": "grandfather's name", "father_name": "father's name",
             "first_name": "first name", "date_of_birth": "birth date", "household_size": "household size"}
    comp_rows = [(plain.get(r.field, r.field.replace("_", " ")), float(r.filled_pct), "var(--c4)" if r.filled_pct < 80 else "var(--c1)",
                  f"{r.field.replace('_', ' ')}: filled in {r.filled_pct}% of registrations")
                 for r in comp.sort_values("filled_pct").itertuples()]
    quality_tab = _panel("quality", "Data quality", "Which errors are most common, and how to stop them happening.", f"""
{_card("Most common errors", "Number of registrations with each problem.",
       '<div class="legend"><span class="lg"><i style="background:' + CRIT + '"></i>Must fix: the record can\'t be used until corrected</span>'
       '<span class="lg"><i style="background:' + WARN + '"></i>Should fix: usable, but needs correcting</span></div>'
       + _hbars(rule_rows, label_w=290, aria="Registrations with each error"), "rules",
       "Each bar is one check the system runs on every registration. Hover over a bar to see the exact number.")}
{_card("Stop errors at the source", "Fixing the registration form is cheaper than cleaning data afterwards.", fixes_html, "fixes")}
{_card("How complete is the data?", "Share of registrations with each field filled in. Yellow fields are below 80%.",
       _hbars(comp_rows, label_w=170, unit="%", aria="Share of registrations with each field filled in"), "completeness",
       "National ID and phone number are the most useful fields for spotting repeats. Low completeness there means more cases need a person to check.")}""")

    # ---------------- Duplicates tab
    dup_tab = _panel("duplicates", "Duplicates", "Examples of people registered more than once, and the pairs a person should check.", f"""
{_card("Examples of repeat registrations found", "Same person, different spelling, birth date or phone format.", _example_clusters(gold, raw), "examples")}
{_card("Pairs for a quick check", "These look alike but aren't certain. A person should confirm each one before merging.",
       '<div class="toolbar"><span>' + _fmt(len(review_rows)) + ' pairs</span><span class="sp"></span>'
       '<button class="btn no-print" id="dlReview">⤓ Download all (CSV)</button></div>'
       '<div class="tbl-wrap" style="max-height:420px;overflow-y:auto"><table id="reviewTbl" class="small"><thead></thead><tbody></tbody></table></div>',
       "review", "Similarity runs from 0 (nothing alike) to 1 (identical). The last column says why the system wasn't sure.")}
{_card("How alike are the compared pairs?", "Each compared pair gets a similarity score between 0 and 1.", _score_hist(scored), "scores",
       f"Blue pairs were judged to be different people. Orange pairs ({REVIEW_AT} to {MATCH_AT}) go to a person. Green pairs ({MATCH_AT} and above) are merged automatically.")}""")

    # ---------------- Performance tab
    perf = []
    if pm:
        b = m["baseline"]
        perf.append(_tiles([
            ("People merged by mistake", _fmt(pm["fp"]), "lower is better", "var(--c3)"),
            ("Repeats caught automatically", _pct(pm["recall"]), f"vs {_pct(b['recall'], 0)} with exact matching", "var(--c1)"),
            ("Comparisons skipped", f"{100 * (1 - summary['candidate_pairs'] / summary['all_possible_pairs']):.1f}%",
             f"only {_fmt(summary['candidate_pairs'])} pairs needed checking", "var(--c2)"),
            ("Processing time", f"{summary['runtime_s']} s", f"for {_fmt(n_in)} registrations", "var(--c4)"),
        ]))
        perf.append(_card("Accuracy compared with exact matching",
                          f"Exact matching (same spelling, same birth date) misses {_pct(1 - b['recall'], 0)} of repeats. This system catches {_pct(pm['recall'])} on its own.",
                          _accuracy_chart(m), "accuracy",
                          "Correct merges (precision): of the records joined together, how many really were the same person. "
                          "Duplicates caught (recall): of all real repeats, how many were found. Overall score (F1) combines the two."))
    if data["curve"]:
        perf.append(_card("Choose the right setting", "Drag the slider to see what happens if the system merges more or less automatically.", f"""
<label for="thr" style="display:block;font-size:13.5px;color:var(--text-secondary);margin-bottom:4px">Merge automatically when similarity is at least
<b id="tVal" style="color:var(--text-primary);font-size:16px">{MATCH_AT}</b> <span style="color:var(--text-muted)">(current setting: {MATCH_AT})</span></label>
<input id="thr" type="range" min="{data['curve'][0]['t']}" max="{data['curve'][-1]['t']}" step="0.01" value="{MATCH_AT}">
<div class="outs">
<div class="out" style="--oc:var(--c3)"><div class="lbl">Merged automatically</div><div class="big" id="tAuto">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Sent to a person</div><div class="big" id="tReview">–</div></div>
<div class="out" style="--oc:var(--c4)"><div class="lbl">Checking time (2 min each)</div><div class="big" id="tHours">–</div></div>
<div class="out" style="--oc:var(--c1)"><div class="lbl">Correct merges</div><div class="big" id="tP">–</div></div>
<div class="out" style="--oc:var(--c2)"><div class="lbl">Repeats caught</div><div class="big" id="tR">–</div></div>
<div class="out" style="--oc:var(--c5)"><div class="lbl">Merged by mistake</div><div class="big" id="tFP">–</div></div></div>
<p class="advice" id="tAdvice"></p>
<div class="legend"><span class="lg"><i style="background:var(--c1)"></i>Correct merges</span><span class="lg"><i style="background:var(--c2)"></i>Duplicates caught</span></div>
{_threshold_chart(data['curve'])}""", "explorer",
            "Moving left merges more automatically but risks joining different people, which could cut someone off assistance. "
            "Moving right is safer but sends more pairs to a person. The dashed line is your choice."))
    if bench:
        rows_b = pd.DataFrame([{"Registrations": _fmt(x["records"]), "Time": f'{x["seconds"]} s',
                                "Per second": _fmt(x["records_per_second"]),
                                "Comparisons skipped": f'{100 * (1 - x["pairs_scored"] / x["all_pairs"]):.2f}%',
                                "Correct merges": _pct(x["precision"]), "Repeats caught": _pct(x["recall"])} for x in bench])
        perf.append(_card("Speed and scale", f"Tested on {len(bench)} data sizes up to {_fmt(bench[-1]['records'])} registrations, on an ordinary laptop-class machine.",
                          _bench_chart(bench) + "<h4>Detailed results</h4>" + _table(rows_b), "scale",
                          "Speed stays steady at about the same number of registrations per second as data grows, and accuracy stays high. "
                          "A national-scale list would run in batches by region."))
    perf.append(_card("Built-in quality checks", "The code checks itself every time it changes.", """
<div class="trust">
<div><b><span class="ok">✓</span>19 automated code tests</b>Phone formats, spelling variants, sibling protection, accuracy on fresh random data.</div>
<div><b><span class="ok">✓</span>29 data tests in the warehouse</b>Unique IDs, valid values, every registration linked to a person.</div>
<div><b><span class="ok">✓</span>Runs on every change</b>GitHub Actions runs everything automatically, and the badge on the code page shows the result.</div>
<div><b><span class="ok">✓</span>Same results every time</b>Fixed rules and settings, so a run can be repeated and audited.</div>
</div>""", "qa"))
    perf_tab = _panel("performance", "Performance", "How accurate, how fast, and how reliable the system is.", "".join(perf))

    # ---------------- How it works tab
    step_cols = ["var(--c1)", "var(--c4)", "var(--c3)", "var(--c2)", "var(--c5)", "var(--c7)"]
    steps = [("Collect", "Registrations come in from the field (here: realistic made-up data with known repeats)."),
             ("Check", f"{len(by_rule)} checks find missing, invalid or unlikely values."),
             ("Tidy", "Names, phone numbers and dates are put in one standard format. A sound-alike key links spellings like Mohammed and Mohamed."),
             ("Shortlist", "Only records that share something (a phone, ID, birth date or similar name) are compared, which skips 99.9% of comparisons."),
             ("Compare", "Each pair is scored on 8 details, with rules for siblings and different national IDs."),
             ("Decide", "Clear matches merge, unclear ones go to a person, and one clean record is kept per person.")]
    steps_html = '<div class="steps">' + "".join(f'<div class="step" style="--sc:{c}"><b>{a}</b>{t}</div>'
                                                 for (a, t), c in zip(steps, step_cols)) + "</div>"
    stack = '<div class="stack">' + "".join(f'<span style="--sc:{c}">{t}</span>' for t, c in zip(
        ["Python", "pandas", "RapidFuzz", "SQL", "dbt", "DuckDB", "BigQuery", "LLM APIs", "pytest", "GitHub Actions"],
        ["var(--c1)", "var(--c1)", "var(--c3)", "var(--c2)", "var(--c2)", "var(--c4)", "var(--c1)", "var(--c7)", "var(--c3)", "var(--c5)"])) + "</div>"
    method_tab = _panel("method", "How it works", "The same steps a registration team follows before a distribution list goes out.", f"""
{_card("Six steps", None, steps_html)}
{_card("Tools used", "Open-source tools that run on a laptop or in the cloud.", stack +
       f'<p class="note" style="margin-top:12px">Run it on your own file: <code>python run_pipeline.py --input your_file.csv</code>. '
       f'Technical documentation of the data models: <a href="{pages}/dbt-docs.html">dbt docs</a>. Source code: '
       f'<a href="https://github.com/{repo}">github.com/{repo}</a>.</p>')}
{_card("Privacy", None, '<p class="lede" style="margin:0">Every record in this report is made up. No real person is represented. '
       'On real data, the system runs inside the organisation\'s own environment, so no personal data has to leave it.</p>')}""")

    # ---------------- Feedback tab
    fb_tab = _panel("feedback", "Feedback", "Tell us what else you need: a new breakdown, a change, or something that looks wrong.", f"""
<section class="card" id="fbCard"><h2>Send a request</h2><p class="lede">Takes about a minute. Each request becomes a tracked item, so you can follow it.</p>
<form id="fbForm" class="fb-grid" novalidate>
<label class="f">Your name (optional)<input id="fbName" type="text" autocomplete="name"></label>
<label class="f">Role or office (optional)<input id="fbRole" type="text" placeholder="e.g. Programme Officer, area office"></label>
<label class="f">What kind of feedback?<select id="fbType"><option>New requirement</option><option>New chart or breakdown</option>
<option>Something looks wrong</option><option>Question</option><option>Other</option></select></label>
<label class="f">Which part of the report?<select id="fbSection"><option>Whole report</option><option>Summary</option><option>Where to act</option>
<option>Data quality</option><option>Duplicates</option><option>Performance</option></select></label>
<label class="f">How urgent?<select id="fbPriority"><option>Nice to have</option><option>Important</option><option>Needed for a decision soon</option></select></label>
<label class="f">Short title<input id="fbSummary" type="text" placeholder="e.g. Show repeats by kebele"></label>
<label class="f full">What do you need, or what did you notice? *<textarea id="fbDetail" required placeholder="Describe it in your own words"></textarea></label>
<label class="f full">What decision would this help you make? (optional)<input id="fbDecision" type="text" placeholder="e.g. Where to send verification teams next month"></label>
<div class="full" style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn primary" type="submit">Prepare request</button>
<a id="fbLink" class="btn" href="#" target="_blank" rel="noopener" style="display:none">Send on GitHub ↗</a>
<button class="btn" type="button" id="fbCopy">Copy text</button></div></form><div id="fbStatus" role="status"></div></section>
{_card("What happens next", None, '<div class="next"><div><b>1. Logged</b>Your request is saved as a tracked item.</div>'
       '<div><b>2. Reviewed</b>It is checked and given a priority.</div><div><b>3. Built</b>The change is made and tested.</div>'
       '<div><b>4. Updated</b>The report refreshes, and you can see it on the request.</div></div>')}""")

    tabs_html = "".join(f'<button class="tab" role="tab" id="tab-{i}" data-tab="{i}" aria-controls="panel-{i}" style="--tc:{c}">'
                        f'<span class="d"></span>{n}</button>' for i, n, c, _, _ in TABS)

    help_drawer = f"""
<div id="scrim" class="scrim"></div>
<aside id="help" class="drawer" aria-hidden="true" aria-label="Help">
<button class="btn x" id="helpClose">Close ✕</button>
<h3>How to use this report</h3>
<p style="color:var(--text-secondary);font-size:13.5px;margin:0">It takes about 5 minutes. Nothing you type is sent anywhere unless you choose to send feedback.</p>
<p><button class="btn primary" data-tour>▶ Take the 1-minute tour</button></p>
<h4>Start with your tab</h4>
<ul><li><b>Managers:</b> <i>Summary</i>. Read "What to do next" and try the money calculator.</li>
<li><b>Area offices and field coordinators:</b> <i>Where to act</i>, for locations and enumerators.</li>
<li><b>Data teams:</b> <i>Data quality</i> and <i>Duplicates</i>.</li>
<li><b>Donors, auditors, reviewers:</b> <i>Performance</i>, to see how much you can trust it.</li></ul>
<h4>Things you can do</h4>
<ul><li>Hover over any bar, dot or line to see the exact number.</li>
<li>Click a column name in a table to sort it, and click again to reverse.</li>
<li>Filter by region, or show only enumerators who need coaching.</li>
<li>Download any list as a spreadsheet (CSV).</li>
<li>Type into the calculator or drag the slider, and the numbers update straight away.</li>
<li>Open "How to read this" under a title for a short explanation.</li>
<li>Share a tab directly: the address ends with its name, for example <code>#performance</code>.</li></ul>
<h4>Words used</h4>
<dl>
<dt>Repeat registration (duplicate)</dt><dd>Someone registered again when they were already on the list.</dd>
<dt>Real people</dt><dd>The number of different people after repeats are removed.</dd>
<dt>Quick check (review)</dt><dd>A pair that looks alike but isn't certain, so a person decides.</dd>
<dt>Similarity</dt><dd>How alike two registrations are, from 0 (nothing alike) to 1 (identical).</dd>
<dt>Correct merges (precision)</dt><dd>Of the records joined together, the share that really were the same person.</dd>
<dt>Repeats caught (recall)</dt><dd>Of all real repeats, the share that were found.</dd>
<dt>Must fix / should fix</dt><dd>Must fix: the record can't be used yet. Should fix: usable but needs correcting.</dd>
</dl>
<h4>Questions</h4>
<dl><dt>Is this real data?</dt><dd>No. Every record is made up. No real person is shown.</dd>
<dt>Can it run on our data?</dt><dd>Yes. The accuracy numbers need known answers, so they only appear for test data.</dd>
<dt>Who decides the setting?</dt><dd>The programme does. The Performance tab shows the trade-off, so the choice can be agreed and written down.</dd>
<dt>Something missing?</dt><dd><a href="#feedback" data-goto="feedback">Send feedback</a>.</dd></dl></aside>
<button class="fab no-print" data-open-help aria-label="Open help">?</button>
<div id="tourBox" role="dialog" aria-live="polite"><p id="tourText"></p><div class="row"><span id="tourCount" style="font-size:12.5px;opacity:.8"></span>
<span style="display:flex;gap:8px"><button class="btn" id="tourEnd">Skip</button><button class="btn" id="tourPrev">Back</button>
<button class="btn" id="tourNext">Next</button></span></div></div>"""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Beneficiary deduplication and data-quality report: repeat registrations, data errors, where to act, and performance.">
<title>Beneficiary Deduplication &amp; Data-Quality Pipeline — Report</title><style>{CSS}</style></head>
<body><div class="viz-root">
<div class="strip"><div class="in"><span>Portfolio project by <b>{E(author)}</b></span>
<a href="https://github.com/{repo}">View the code</a><a href="{pages}/dbt-docs.html">Technical docs</a></div></div>
<div class="wrap">
<header class="hero"><h1>Who is really on the list?</h1>
<p>This report checks beneficiary registrations for errors, finds people registered more than once, even with different spellings,
birth dates or phone formats, and shows managers where to act.</p>
<div class="chips"><span class="chip">Made-up test data: no real people</span><span class="chip">Updated {date.today().strftime('%d %b %Y')}</span>
<span class="chip">{_fmt(n_in)} registrations</span><button class="btn primary" data-tour>▶ 1-minute tour</button>
<button class="btn no-print" data-print>Print / save as PDF</button></div></header>
<nav class="tabs" role="tablist" aria-label="Report sections">{tabs_html}<span class="sp"></span>
<button class="btn no-print" data-open-help>Help</button></nav>
{summary_tab}{act_tab}{quality_tab}{dup_tab}{perf_tab}{method_tab}{fb_tab}
<footer>Built by {E(author)} with Python, SQL and dbt · <a href="https://github.com/{repo}">Source code</a></footer>
</div>{help_drawer}<div id="tip" role="tooltip"></div></div>
<script type="application/json" id="report-data">{data_json}</script>
<script>{JS}</script></body></html>"""
