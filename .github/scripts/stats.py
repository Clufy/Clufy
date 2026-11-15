"""Render GitHub stats + top-language cards (dark/light SVG) for the profile README.

Runs in GitHub Actions with GH_TOKEN (the workflow's GITHUB_TOKEN) and GH_USER set.
Writes stats-dark.svg, stats-light.svg, langs-dark.svg, langs-light.svg into the output dir.
Stdlib only.
"""
import json
import os
import sys
import urllib.request
from html import escape

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
  }
}
"""

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", fg="#e6edf3", muted="#8b949e", track="#21262d", accent="#58a6ff"),
    "light": dict(bg="#ffffff", border="#d0d7de", fg="#1f2328", muted="#59636e", track="#eaeef2", accent="#0969da"),
}
SANS = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
EXCLUDE = {"Jupyter Notebook", "HTML"}  # notebook JSON and markup inflate byte counts


def fetch(user, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]


def summarize(u):
    repos = u["repositories"]["nodes"]
    cc = u["contributionsCollection"]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n in EXCLUDE:
                continue
            langs.setdefault(n, [0, e["node"]["color"] or "#8b949e"])[0] += e["size"]
    total = sum(v[0] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    return {
        "stats": [
            ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
            ("Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
            ("Pull requests", u["pullRequests"]["totalCount"]),
            ("Public repositories", u["repositories"]["totalCount"]),
            ("Stars earned", sum(r["stargazerCount"] for r in repos)),
            ("Followers", u["followers"]["totalCount"]),
        ],
        "langs": [(n, v[0] / total, v[1]) for n, (v) in top],
    }


def card(w, h, t, title, body):
    css = (f"text{{font-family:{SANS};fill:{t['fg']}}}.m{{fill:{t['muted']}}}.n{{font-family:{MONO};font-weight:700}}"
           ".row{opacity:0;animation:in .5s ease-out forwards}@keyframes in{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:none}}"
           ".bar{transform-box:fill-box;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) forwards;transform:scaleX(0)}"
           "@keyframes grow{to{transform:scaleX(1)}}@media (prefers-reduced-motion:reduce){.row,.bar{animation:none;opacity:1;transform:none}}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">'
            f"<title>{escape(title)}</title><style>{css}</style>"
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<rect x="24" y="26" width="28" height="4" rx="2" fill="{t["accent"]}"/>'
            f'<text x="24" y="54" style="font-size:17px;font-weight:800">{escape(title)}</text>{body}</svg>')


def stats_svg(s, t):
    rows = []
    items = [(label, val) for label, val in s["stats"] if val]  # hide zero-valued rows
    for i, (label, val) in enumerate(items):
        y = 92 + i * 30
        rows.append(f'<g class="row" style="animation-delay:{i * .12:.2f}s">'
                    f'<text x="24" y="{y}" class="m" style="font-size:14px">{escape(label)}</text>'
                    f'<text x="396" y="{y}" text-anchor="end" class="n" style="font-size:15px">{val:,}</text></g>')
    return card(420, 92 + len(items) * 30 - 6, t, "GitHub activity", "".join(rows))


def langs_svg(s, t):
    rows = []
    for i, (name, frac, color) in enumerate(s["langs"]):
        y = 88 + i * 30
        rows.append(f'<g class="row" style="animation-delay:{i * .12:.2f}s">'
                    f'<circle cx="30" cy="{y - 5}" r="5" fill="{color}"/>'
                    f'<text x="44" y="{y}" style="font-size:14px">{escape(name)}</text>'
                    f'<text x="396" y="{y}" text-anchor="end" class="n m" style="font-size:13px">{frac * 100:.1f}%</text>'
                    f'<rect x="196" y="{y - 9}" width="140" height="8" rx="4" fill="{t["track"]}"/>'
                    f'<rect class="bar" style="animation-delay:{.2 + i * .12:.2f}s" x="196" y="{y - 9}" width="{max(4, 140 * frac):.1f}" height="8" rx="4" fill="{color}"/></g>')
    return card(420, 88 + max(1, len(s["langs"])) * 30 - 2, t, "Top languages", "".join(rows))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "dist"
    os.makedirs(out, exist_ok=True)
    if os.environ.get("STATS_FIXTURE"):
        s = json.load(open(os.environ["STATS_FIXTURE"]))
    else:
        s = summarize(fetch(os.environ["GH_USER"], os.environ["GH_TOKEN"]))
    for name, t in THEMES.items():
        open(os.path.join(out, f"stats-{name}.svg"), "w").write(stats_svg(s, t))
        open(os.path.join(out, f"langs-{name}.svg"), "w").write(langs_svg(s, t))
    print("wrote cards to", out)


if __name__ == "__main__":
    main()
