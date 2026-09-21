#!/usr/bin/env python3
"""Generate one combined SVG: pipeline stats + isometric contribution calendar.

Produces assets/profile-card-day.svg and assets/profile-card-night.svg, each
a single card (one background, one border) so the README can swap between
them with a <picture> tag instead of stitching two separate images together.
"""
import datetime
import os
import re
import urllib.request
import urllib.error
import json

OWNER = "DenGuleDansker"
REPOS = ["discordBot", "AgentStatusHook", "react-resume", "portfolio-html"]
# NOTE: the default `secrets.GITHUB_TOKEN` in Actions is scoped only to the
# repo the workflow runs in, so using it to read Actions data on the other
# (public) repos below returns 404. These repos are public, so unauthenticated
# calls work fine within the 60 req/hour anonymous limit. Set DASHBOARD_TOKEN
# (a PAT with public_repo scope) as a repo secret only if more headroom is
# ever needed.
TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

CONTRIB_URLS = {
    "day": "https://raw.githubusercontent.com/DenGuleDansker/DenGuleDansker/output-3d-contrib/day.svg",
    "night": "https://raw.githubusercontent.com/DenGuleDansker/DenGuleDansker/output-3d-contrib/night.svg",
}

# Matches the portfolio-html palette (--bg-card, --bg-hero, --steel, --accent).
# The contrib calendar's own backgroundColor (conf/github-profile-3d-contrib.json)
# is set to the same BG values so it blends into this card with no visible seam.
THEMES = {
    "night": dict(
        BG="#0a1f2e", SURFACE="#0d2538", BORDER="#1a3a52",
        TEXT="#d6e0e8", TEXT_MUTED="#8fafc4", ACCENT="#b26617",
        SUCCESS="#3fa860", FAILURE="#d4574a", CANCELLED="#5f8299",
    ),
    "day": dict(
        BG="#ffffff", SURFACE="#ddeaf4", BORDER="#b0cfe0",
        TEXT="#0a1f2e", TEXT_MUTED="#3a6070", ACCENT="#b26617",
        SUCCESS="#2f8f52", FAILURE="#c14536", CANCELLED="#5c7c90",
    ),
}
FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"


def http_get(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{OWNER}-pipeline-dashboard",
    })
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        print(f"::error::Failed fetching {url} -> HTTP {e.code}: {e.read().decode()[:300]}")
        raise


def fetch_runs(repo):
    url = f"https://api.github.com/repos/{OWNER}/{repo}/actions/runs?per_page=100"
    runs = []
    while url:
        body, headers = http_get(url)
        data = json.loads(body)
        runs.extend(data.get("workflow_runs", []))
        url = None
        for part in headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return runs


def fetch_contrib_svg(variant):
    body, _ = http_get(CONTRIB_URLS[variant])
    m = re.search(r'viewBox="([\d.\s]+)"', body)
    vb = m.group(1) if m else "0 0 1280 850"
    inner = re.sub(r"^.*?<svg[^>]*>", "", body, count=1, flags=re.S)
    inner = re.sub(r"</svg>\s*$", "", inner, count=1, flags=re.S)
    vw, vh = (float(x) for x in vb.split()[2:4])
    return inner, vw, vh


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        "repo": repo, "total": total, "success": success, "failure": failure,
        "cancelled": cancelled, "workflows": workflows, "last": last, "active": active,
    }


def bar_segments(x, y, w, h, stats, c, radius=3):
    total = stats["total"] or 1
    parts = [(stats["success"], c["SUCCESS"]), (stats["failure"], c["FAILURE"]), (stats["cancelled"], c["CANCELLED"])]
    svg = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{c["SURFACE"]}"/>']
    cx = x
    for count, color in parts:
        if count <= 0:
            continue
        seg_w = w * count / total
        svg.append(f'<rect x="{cx:.1f}" y="{y}" width="{seg_w:.1f}" height="{h}" fill="{color}"/>')
        cx += seg_w
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="none" stroke="{c["BORDER"]}"/>')
    return "\n".join(svg)


def render_svg(all_stats, variant, contrib_inner, contrib_vw, contrib_vh):
    c = THEMES[variant]
    width = 880
    pad = 28
    content_w = width - 2 * pad
    body = []
    y = 0

    # header
    y += 34
    body.append(f'<text x="{pad}" y="{y}" font-size="11" letter-spacing="1.5" fill="{c["ACCENT"]}" font-weight="600">{esc(OWNER.upper())} · GITHUB</text>')
    y += 28
    body.append(f'<text x="{pad}" y="{y}" font-size="22" fill="{c["TEXT"]}" font-weight="600">Pipelines &amp; Contributions</text>')
    y += 22
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    total_runs = sum(s["total"] for s in all_stats)
    body.append(f'<text x="{pad}" y="{y}" font-size="12" fill="{c["TEXT_MUTED"]}">Auto-updated {esc(today)} · {len(all_stats)} repositories · {total_runs} runs total</text>')
    y += 18

    # stat tiles
    total_success = sum(s["success"] for s in all_stats)
    total_failure = sum(s["failure"] for s in all_stats)
    active_count = sum(1 for s in all_stats if s["active"])
    success_rate = (100 * total_success / total_runs) if total_runs else 0
    tile_h = 70
    tile_w = (content_w - 3 * 12) / 4
    tiles = [
        (str(total_runs), "Total runs", c["TEXT"]),
        (f"{success_rate:.0f}%", "Success rate", c["SUCCESS"]),
        (str(active_count), "Active last 7 days", c["ACCENT"]),
        (str(total_failure), "Failed runs", c["FAILURE"] if total_failure else c["TEXT_MUTED"]),
    ]
    for i, (num, label, color) in enumerate(tiles):
        tx = pad + i * (tile_w + 12)
        body.append(f'<rect x="{tx:.1f}" y="{y}" width="{tile_w:.1f}" height="{tile_h}" rx="8" fill="{c["SURFACE"]}" stroke="{c["BORDER"]}"/>')
        body.append(f'<text x="{tx+14:.1f}" y="{y+32}" font-size="22" fill="{color}" font-weight="600">{esc(num)}</text>')
        body.append(f'<text x="{tx+14:.1f}" y="{y+50}" font-size="11" fill="{c["TEXT_MUTED"]}">{esc(label)}</text>')
    y += tile_h + 26

    # repo rows
    row_h = 78
    for s in all_stats:
        ry = y
        body.append(f'<rect x="{pad}" y="{ry}" width="{content_w}" height="{row_h}" rx="10" fill="{c["SURFACE"]}" stroke="{c["BORDER"]}"/>')
        body.append(f'<text x="{pad+20}" y="{ry+26}" font-size="14" fill="{c["TEXT"]}" font-weight="600">{esc(s["repo"])}</text>')
        wf = " + ".join(s["workflows"]) if s["workflows"] else "—"
        body.append(f'<text x="{pad+20}" y="{ry+42}" font-size="11" fill="{c["TEXT_MUTED"]}">{esc(wf)}</text>')

        tag = "active" if s["active"] else "dormant"
        tag_color = c["SUCCESS"] if s["active"] else c["TEXT_MUTED"]
        tag_w = 58
        tag_x = pad + content_w - 20 - tag_w
        body.append(f'<rect x="{tag_x:.1f}" y="{ry+14}" width="{tag_w}" height="20" rx="10" fill="{c["BG"]}" stroke="{tag_color}"/>')
        body.append(f'<text x="{tag_x+tag_w/2:.1f}" y="{ry+28}" font-size="10" fill="{tag_color}" text-anchor="middle" font-weight="600">{tag}</text>')

        bar_w = 220
        body.append(bar_segments(pad+20, ry + 52, bar_w, 8, s, c))
        rate = (100 * s["success"] / s["total"]) if s["total"] else 0
        body.append(f'<text x="{pad+20+bar_w+12}" y="{ry+59}" font-size="11" fill="{c["TEXT_MUTED"]}">{s["total"]} runs · {rate:.0f}% success</text>')

        if s["last"]:
            last_dt = datetime.datetime.fromisoformat(s["last"]["created_at"].replace("Z", "+00:00"))
            last_str = last_dt.strftime("%d %b %Y, %H:%M")
            concl = s["last"]["conclusion"] or "unknown"
            dot_color = {"success": c["SUCCESS"], "failure": c["FAILURE"], "cancelled": c["CANCELLED"]}.get(concl, c["TEXT_MUTED"])
            last_label = f'last: {concl} · {last_str}'
        else:
            dot_color = c["TEXT_MUTED"]
            last_label = "no runs yet"
        body.append(f'<circle cx="{pad+24}" cy="{ry+70}" r="3.5" fill="{dot_color}"/>')
        body.append(f'<text x="{pad+34}" y="{ry+73}" font-size="11" fill="{c["TEXT_MUTED"]}">{esc(last_label)}</text>')
        y += row_h + 10

    y += 16

    # contribution calendar, embedded and scaled to the card's content width
    body.append(f'<text x="{pad}" y="{y+12}" font-size="11" letter-spacing="1.5" fill="{c["ACCENT"]}" font-weight="600">CONTRIBUTIONS</text>')
    y += 26
    scale = content_w / contrib_vw
    cal_h = contrib_vh * scale
    body.append(
        f'<svg x="{pad}" y="{y}" width="{content_w:.1f}" height="{cal_h:.1f}" '
        f'viewBox="0 0 {contrib_vw:.0f} {contrib_vh:.0f}">{contrib_inner}</svg>'
    )
    y += cal_h + 20

    body.append(f'<text x="{pad}" y="{y+10}" font-size="10" fill="{c["TEXT_MUTED"]}">Generated by a scheduled GitHub Action · github.com/{OWNER}/{OWNER}</text>')
    y += 24

    height = y
    head = [
        f'<svg width="{width}" height="{height:.0f}" viewBox="0 0 {width} {height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">',
        f'<rect width="{width}" height="{height:.0f}" rx="14" fill="{c["BG"]}"/>',
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1:.0f}" rx="13.5" fill="none" stroke="{c["BORDER"]}"/>',
    ]
    return "\n".join(head + body + ["</svg>"])


def main():
    all_stats = [build_repo_stats(r) for r in REPOS]
    os.makedirs(OUT_DIR, exist_ok=True)
    for variant in ("day", "night"):
        contrib_inner, cvw, cvh = fetch_contrib_svg(variant)
        svg = render_svg(all_stats, variant, contrib_inner, cvw, cvh)
        out_path = os.path.join(OUT_DIR, f"profile-card-{variant}.svg")
        with open(out_path, "w") as f:
            f.write(svg)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
