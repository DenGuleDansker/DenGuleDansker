#!/usr/bin/env python3
"""Generate a static SVG pipeline dashboard from GitHub Actions run data."""
import datetime
import os
import urllib.request
import json

OWNER = "DenGuleDansker"
REPOS = ["discordBot", "AgentStatusHook", "react-resume", "telegram-bot", "portfolio-html"]
# NOTE: the default `secrets.GITHUB_TOKEN` in Actions is scoped only to the
# repo the workflow runs in, so using it to read Actions data on the other
# (public) repos below returns 404. These repos are public, so unauthenticated
# calls work fine within the 60 req/hour anonymous limit (5 repos per run).
# Set DASHBOARD_TOKEN (a PAT with public_repo scope) as a repo secret only if
# more headroom is ever needed.
TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "pipeline-dashboard.svg")

BG = "#0D1117"
SURFACE = "#161B22"
BORDER = "#2B323C"
TEXT = "#E6EDF3"
TEXT_MUTED = "#8B94A1"
ACCENT = "#818CF8"
SUCCESS = "#3FB950"
FAILURE = "#F85149"
CANCELLED = "#8B949E"
FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"


def fetch_runs(repo):
    url = f"https://api.github.com/repos/{OWNER}/{repo}/actions/runs?per_page=100"
    runs = []
    while url:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if TOKEN:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            link = resp.headers.get("Link", "")
        runs.extend(data.get("workflow_runs", []))
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return runs


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_repo_stats(repo):
    runs = fetch_runs(repo)
    total = len(runs)
    success = sum(1 for r in runs if r["conclusion"] == "success")
    failure = sum(1 for r in runs if r["conclusion"] == "failure")
    cancelled = sum(1 for r in runs if r["conclusion"] == "cancelled")
    workflows = sorted({r["name"] for r in runs})
    last = runs[0] if runs else None
    now = datetime.datetime.now(datetime.timezone.utc)
    active = False
    if last:
        last_dt = datetime.datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))
        active = (now - last_dt).days <= 7
    return {
        "repo": repo,
        "total": total,
        "success": success,
        "failure": failure,
        "cancelled": cancelled,
        "workflows": workflows,
        "last": last,
        "active": active,
    }


def bar_segments(x, y, w, h, stats, radius=3):
    total = stats["total"] or 1
    parts = [
        (stats["success"], SUCCESS),
        (stats["failure"], FAILURE),
        (stats["cancelled"], CANCELLED),
    ]
    svg = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{SURFACE}"/>']
    cx = x
    for count, color in parts:
        if count <= 0:
            continue
        seg_w = w * count / total
        svg.append(f'<rect x="{cx:.1f}" y="{y}" width="{seg_w:.1f}" height="{h}" fill="{color}"/>')
        cx += seg_w
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="none" stroke="{BORDER}"/>')
    return "\n".join(svg)


def render_svg(all_stats):
    width = 880
    row_h = 78
    header_h = 96
    stats_h = 84
    footer_h = 34
    list_top = header_h + stats_h + 28
    height = list_top + len(all_stats) * (row_h + 10) + footer_h

    total_runs = sum(s["total"] for s in all_stats)
    total_success = sum(s["success"] for s in all_stats)
    total_failure = sum(s["failure"] for s in all_stats)
    active_count = sum(1 for s in all_stats if s["active"])
    success_rate = (100 * total_success / total_runs) if total_runs else 0

    parts = []
    parts.append(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>')
    parts.append(f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="13.5" fill="none" stroke="{BORDER}"/>')

    # header
    parts.append(f'<text x="28" y="34" font-size="11" letter-spacing="1.5" fill="{ACCENT}" font-weight="600">{esc(OWNER.upper())} · GITHUB ACTIONS</text>')
    parts.append(f'<text x="28" y="62" font-size="22" fill="{TEXT}" font-weight="600">Pipeline Overview</text>')
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    parts.append(f'<text x="28" y="84" font-size="12" fill="{TEXT_MUTED}">Auto-updated {esc(today)} · {len(all_stats)} repositories · {total_runs} runs total</text>')

    # stat tiles
    tile_w = (width - 56 - 3 * 12) / 4
    tile_y = header_h
    tiles = [
        (str(total_runs), "Total runs", TEXT),
        (f"{success_rate:.0f}%", "Success rate", SUCCESS),
        (str(active_count), "Active last 7 days", ACCENT),
        (str(total_failure), "Failed runs", FAILURE if total_failure else TEXT_MUTED),
    ]
    for i, (num, label, color) in enumerate(tiles):
        tx = 28 + i * (tile_w + 12)
        parts.append(f'<rect x="{tx:.1f}" y="{tile_y}" width="{tile_w:.1f}" height="{stats_h-14}" rx="8" fill="{SURFACE}" stroke="{BORDER}"/>')
        parts.append(f'<text x="{tx+14:.1f}" y="{tile_y+32}" font-size="22" fill="{color}" font-weight="600">{esc(num)}</text>')
        parts.append(f'<text x="{tx+14:.1f}" y="{tile_y+50}" font-size="11" fill="{TEXT_MUTED}">{esc(label)}</text>')

    # repo rows
    for i, s in enumerate(all_stats):
        ry = list_top + i * (row_h + 10)
        parts.append(f'<rect x="28" y="{ry}" width="{width-56}" height="{row_h}" rx="10" fill="{SURFACE}" stroke="{BORDER}"/>')
        parts.append(f'<text x="48" y="{ry+26}" font-size="14" fill="{TEXT}" font-weight="600">{esc(s["repo"])}</text>')
        wf = " + ".join(s["workflows"]) if s["workflows"] else "—"
        parts.append(f'<text x="48" y="{ry+42}" font-size="11" fill="{TEXT_MUTED}">{esc(wf)}</text>')

        tag = "active" if s["active"] else "dormant"
        tag_color = SUCCESS if s["active"] else TEXT_MUTED
        tag_w = 58
        parts.append(f'<rect x="{width-56-28-tag_w}" y="{ry+14}" width="{tag_w}" height="20" rx="10" fill="{BG}" stroke="{tag_color}"/>')
        parts.append(f'<text x="{width-56-28-tag_w+tag_w/2:.1f}" y="{ry+28}" font-size="10" fill="{tag_color}" text-anchor="middle" font-weight="600">{tag}</text>')

        bar_w = 220
        parts.append(bar_segments(48, ry + 52, bar_w, 8, s))
        rate = (100 * s["success"] / s["total"]) if s["total"] else 0
        parts.append(f'<text x="{48+bar_w+12}" y="{ry+59}" font-size="11" fill="{TEXT_MUTED}">{s["total"]} runs · {rate:.0f}% success</text>')

        if s["last"]:
            last_dt = datetime.datetime.fromisoformat(s["last"]["created_at"].replace("Z", "+00:00"))
            last_str = last_dt.strftime("%d %b %Y, %H:%M")
            concl = s["last"]["conclusion"] or "unknown"
            dot_color = {"success": SUCCESS, "failure": FAILURE, "cancelled": CANCELLED}.get(concl, TEXT_MUTED)
            label = f'last: {concl} · {last_str}'
        else:
            dot_color = TEXT_MUTED
            label = "no runs yet"
        parts.append(f'<circle cx="52" cy="{ry+70}" r="3.5" fill="{dot_color}"/>')
        parts.append(f'<text x="62" y="{ry+73}" font-size="11" fill="{TEXT_MUTED}">{esc(label)}</text>')

    parts.append(f'<text x="28" y="{height-14}" font-size="10" fill="{TEXT_MUTED}">Generated by a scheduled GitHub Action · github.com/{OWNER}/{OWNER}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    all_stats = [build_repo_stats(r) for r in REPOS]
    svg = render_svg(all_stats)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(svg)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
