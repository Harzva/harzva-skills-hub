#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    return json.loads((ROOT / "meta.config.json").read_text(encoding="utf-8"))


def token() -> str | None:
    return os.environ.get("META_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api_json(url: str, auth_token: str | None) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "meta-repo-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def normalize_repo(raw: dict) -> dict:
    full_name = raw.get("full_name") or raw.get("nameWithOwner")
    language = raw.get("language")
    if isinstance(raw.get("primaryLanguage"), dict):
        primary_language = raw["primaryLanguage"]
    else:
        primary_language = {"name": language} if language else None
    return {
        "name": raw.get("name") or full_name.split("/", 1)[1],
        "nameWithOwner": full_name,
        "url": raw.get("html_url") or raw.get("url"),
        "description": raw.get("description"),
        "isPrivate": bool(raw.get("private") if "private" in raw else raw.get("isPrivate")),
        "isArchived": bool(raw.get("archived") if "archived" in raw else raw.get("isArchived")),
        "isFork": bool(raw.get("fork") if "fork" in raw else raw.get("isFork")),
        "primaryLanguage": primary_language,
        "pushedAt": raw.get("pushed_at") or raw.get("pushedAt"),
        "updatedAt": raw.get("updated_at") or raw.get("updatedAt"),
        "createdAt": raw.get("created_at") or raw.get("createdAt"),
        "defaultBranchRef": raw.get("defaultBranchRef") or {"name": raw.get("default_branch")},
        "homepageUrl": raw.get("homepage") or raw.get("homepageUrl") or "",
        "stargazerCount": raw.get("stargazers_count", raw.get("stargazerCount", 0)),
        "forkCount": raw.get("forks_count", raw.get("forkCount", 0)),
        "repositoryTopics": raw.get("topics") or raw.get("repositoryTopics") or [],
        "openGraphImageUrl": raw.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/meta/{full_name}",
        "pages": raw.get("pages") or {"enabled": False},
        "latestRelease": raw.get("latestRelease"),
    }


def fetch_repos(owner: str, include_private: bool) -> list[dict]:
    auth_token = token()
    repos: list[dict] = []
    page = 1
    while True:
        if include_private and auth_token:
            url = f"https://api.github.com/user/repos?affiliation=owner&per_page=100&sort=updated&page={page}"
        else:
            url = f"https://api.github.com/users/{owner}/repos?type=owner&per_page=100&sort=updated&page={page}"
        chunk = api_json(url, auth_token)
        if not chunk:
            break
        for raw in chunk:
            repo = normalize_repo(raw)
            if not repo["nameWithOwner"].lower().startswith(owner.lower() + "/"):
                continue
            if repo["isPrivate"] and not include_private:
                continue
            repos.append(repo)
        if len(chunk) < 100:
            break
        page += 1

    for repo in repos:
        owner_name, repo_name = repo["nameWithOwner"].split("/", 1)
        pages = api_json(f"https://api.github.com/repos/{owner_name}/{repo_name}/pages", auth_token)
        if pages:
            repo["pages"] = {
                "enabled": True,
                "url": pages.get("html_url"),
                "status": pages.get("status"),
                "source": pages.get("source"),
                "httpsEnforced": pages.get("https_enforced"),
            }
        else:
            repo["pages"] = {"enabled": False}
        release = api_json(f"https://api.github.com/repos/{owner_name}/{repo_name}/releases/latest", auth_token)
        if release:
            repo["latestRelease"] = {
                "name": release.get("name") or release.get("tag_name"),
                "tagName": release.get("tag_name"),
                "url": release.get("html_url"),
                "publishedAt": release.get("published_at"),
                "prerelease": release.get("prerelease"),
                "draft": release.get("draft"),
            }
        else:
            repo["latestRelease"] = None
    return sorted(repos, key=lambda item: (item["isFork"], item["nameWithOwner"].lower()))


def read_source(path: str | None) -> list[dict]:
    if not path:
        return []
    return [normalize_repo(item) for item in json.loads((ROOT / path).read_text(encoding="utf-8"))]


def repo_text(repo: dict) -> str:
    topics = repo.get("repositoryTopics") or []
    if isinstance(topics, list):
        topic_text = " ".join(str(topic) for topic in topics)
    else:
        topic_text = str(topics)
    return " ".join(
        [
            repo.get("name") or "",
            repo.get("description") or "",
            (repo.get("primaryLanguage") or {}).get("name") or "",
            topic_text,
        ]
    ).lower()


def is_skill(repo: dict) -> bool:
    text = repo_text(repo)
    return any(marker in text for marker in ["skill", "codex skill", "plugin", "workflow skill"])


def category(repo: dict) -> str:
    text = repo_text(repo)
    language = ((repo.get("primaryLanguage") or {}).get("name") or "").lower()
    if repo.get("isFork"):
        return "Forks"
    if repo.get("isArchived"):
        return "Archived"
    if is_skill(repo):
        return "Skills and Agent Workflows"
    if repo.get("pages", {}).get("enabled"):
        return "Pages and Live Demos"
    if repo.get("latestRelease"):
        return "Release-ready Apps and Tools"
    if any(x in text for x in ["agent", "llm", "rag", "codex", "claude", "gpt", "ai "]):
        return "AI Agents and LLM Systems"
    if any(x in text for x in ["roadmap", "awesome", "learning", "course", "thesis", "paper", "knowledge"]):
        return "Knowledge Maps and Learning"
    if any(x in text for x in ["tool", "cli", "extension", "sdk", "route", "linux"]) or language in {"rust", "shell"}:
        return "Developer Tools and Infrastructure"
    if language in {"javascript", "typescript", "html", "css", "dart"} or any(x in text for x in ["web", "app", "mobile", "frontend"]):
        return "Apps and Interfaces"
    if language in {"python", "jupyter notebook", "java", "matlab"}:
        return "Research, Data, and Experiments"
    return "Labs and Utilities"


def grouped(repos: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for repo in repos:
        groups.setdefault(category(repo), []).append(repo)
    preferred = [
        "AI Agents and LLM Systems",
        "Pages and Live Demos",
        "Release-ready Apps and Tools",
        "Skills and Agent Workflows",
        "Developer Tools and Infrastructure",
        "Apps and Interfaces",
        "Knowledge Maps and Learning",
        "Research, Data, and Experiments",
        "Labs and Utilities",
        "Archived",
        "Forks",
    ]
    ordered: dict[str, list[dict]] = {}
    for name in preferred:
        if name in groups:
            ordered[name] = sorted(groups[name], key=lambda item: item.get("pushedAt") or "", reverse=True)
    for name in sorted(set(groups) - set(ordered)):
        ordered[name] = groups[name]
    return ordered


def display_date(value: str | None) -> str:
    return (value or "")[:10]


def lang(repo: dict) -> str:
    return (repo.get("primaryLanguage") or {}).get("name") or "Mixed"


def md(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def repo_link(repo: dict) -> str:
    return f"[{md(repo['name'])}]({repo['url']})"


def summary(repos: list[dict], config: dict) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "owner": config["owner"],
        "mode": config["mode"],
        "publicRepositories": len([repo for repo in repos if not repo.get("isPrivate")]),
        "forks": len([repo for repo in repos if repo.get("isFork")]),
        "pages": len([repo for repo in repos if repo.get("pages", {}).get("enabled")]),
        "releases": len([repo for repo in repos if repo.get("latestRelease")]),
        "skills": len([repo for repo in repos if is_skill(repo)]),
        "privateOmitted": config.get("privateOmitted", 0),
    }


def table_for_repos(repos: list[dict]) -> list[str]:
    lines = ["| Repository | Language | Stars | Forks | Updated | Description |", "|---|---:|---:|---:|---:|---|"]
    for repo in repos:
        lines.append(
            f"| {repo_link(repo)} | {md(lang(repo))} | {repo.get('stargazerCount', 0)} | {repo.get('forkCount', 0)} | {display_date(repo.get('pushedAt'))} | {md(repo.get('description') or '')} |"
        )
    return lines


def render_atlas_readme(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]]) -> str:
    hub_links = config["hubLinks"]
    lines = [
        '<div align="center">',
        "",
        "# Harzva Project Atlas",
        "",
        "Harzva 的公开项目地图：把 GitHub 仓库、Release、Pages、Skills 和 fork 统一收纳为一张可自动更新的导航表。",
        "",
        f"[Release Hub]({hub_links['release']}) · [Pages Hub]({hub_links['pages']}) · [Skills Hub]({hub_links['skills']}) · [Owner](https://github.com/{config['owner']})",
        "",
        f"![Repositories](https://img.shields.io/badge/public_repos-{stats['publicRepositories']}-111111?style=for-the-badge) ![Pages](https://img.shields.io/badge/pages-{stats['pages']}-2D9CDB?style=for-the-badge) ![Releases](https://img.shields.io/badge/releases-{stats['releases']}-F05A28?style=for-the-badge) ![Skills](https://img.shields.io/badge/skills-{stats['skills']}-6B8E23?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Meta Hubs",
        "",
        "| Hub | Purpose |",
        "|---|---|",
        f"| [harzva-release-hub]({hub_links['release']}) | Latest releases, downloadable artifacts, and version entry points. |",
        f"| [harzva-pages-hub]({hub_links['pages']}) | A visual gallery of every detected GitHub Pages site and demo. |",
        f"| [harzva-skills-hub]({hub_links['skills']}) | Codex skills, workflow skills, and agent operating recipes. |",
        "",
        "## Category Index",
        "",
        "| Category | Repositories |",
        "|---|---:|",
    ]
    for name, items in groups.items():
        if name != "Forks":
            lines.append(f"| {name} | {len(items)} |")
    lines.append("")
    for name, items in groups.items():
        if name == "Forks":
            continue
        lines.extend([f"## {name}", ""])
        lines.extend(table_for_repos(items))
        lines.append("")
    forks = groups.get("Forks", [])
    if forks:
        lines.extend(["## Forks", "", "Forked repositories are kept at the tail so original Harzva projects remain easy to scan.", ""])
        lines.extend(table_for_repos(forks))
        lines.append("")
    lines.extend(auto_update_section(config, stats))
    return "\n".join(lines)


def render_release_readme(repos: list[dict], config: dict, stats: dict) -> str:
    release_repos = sorted([repo for repo in repos if repo.get("latestRelease")], key=lambda item: item["latestRelease"].get("publishedAt") or "", reverse=True)
    lines = [
        '<div align="center">',
        "",
        "# Harzva Release Hub",
        "",
        "A living release board for Harzva projects with published GitHub releases.",
        "",
        f"[Project Atlas]({config['hubLinks']['atlas']}) · [Owner](https://github.com/{config['owner']})",
        "",
        f"![Releases](https://img.shields.io/badge/releases-{len(release_repos)}-F05A28?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-111111?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Latest Releases",
        "",
        "| Project | Version | Published | Language | Description |",
        "|---|---:|---:|---:|---|",
    ]
    for repo in release_repos:
        release = repo["latestRelease"]
        lines.append(
            f"| {repo_link(repo)} | [{md(release.get('tagName') or release.get('name'))}]({release.get('url')}) | {display_date(release.get('publishedAt'))} | {md(lang(repo))} | {md(repo.get('description') or '')} |"
        )
    lines.extend(["", "## Release Candidates", "", "Projects without a release are tracked in the Atlas first; promote them here after the first tagged release.", ""])
    lines.extend(auto_update_section(config, stats))
    return "\n".join(lines)


def render_pages_readme(repos: list[dict], config: dict, stats: dict) -> str:
    pages = sorted([repo for repo in repos if repo.get("pages", {}).get("enabled")], key=lambda item: item.get("pushedAt") or "", reverse=True)
    lines = [
        '<div align="center">',
        "",
        "# Harzva Pages Hub",
        "",
        "A visual wall for Harzva GitHub Pages sites, demos, docs, and live project surfaces.",
        "",
        f"[Open the gallery](https://{config['owner'].lower()}.github.io/harzva-pages-hub/) · [Project Atlas]({config['hubLinks']['atlas']})",
        "",
        f"![Pages](https://img.shields.io/badge/pages-{len(pages)}-2D9CDB?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-111111?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Gallery Preview",
        "",
        "| Preview | Site | Project | Updated |",
        "|---|---|---|---:|",
    ]
    for repo in pages[:12]:
        page_url = repo.get("pages", {}).get("url") or repo.get("homepageUrl") or repo["url"]
        image = repo.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/meta/{repo['nameWithOwner']}"
        lines.append(
            f"| <img src=\"{image}\" width=\"260\" /> | [{md(repo['name'])}]({page_url}) | [{md(repo['nameWithOwner'])}]({repo['url']}) | {display_date(repo.get('pushedAt'))} |"
        )
    lines.extend(["", "## All Pages", ""])
    lines.extend(table_for_repos(pages))
    lines.append("")
    lines.extend(auto_update_section(config, stats))
    return "\n".join(lines)


def render_skills_readme(repos: list[dict], config: dict, stats: dict) -> str:
    skills = sorted([repo for repo in repos if is_skill(repo)], key=lambda item: item.get("pushedAt") or "", reverse=True)
    lines = [
        '<div align="center">',
        "",
        "# Harzva Skills Hub",
        "",
        "A registry of Harzva Codex skills, workflow skills, and agent operating recipes.",
        "",
        f"[Project Atlas]({config['hubLinks']['atlas']}) · [Owner](https://github.com/{config['owner']})",
        "",
        f"![Skills](https://img.shields.io/badge/skills-{len(skills)}-6B8E23?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-111111?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Skill Registry",
        "",
        "| Skill Repository | Language | Updated | Description |",
        "|---|---:|---:|---|",
    ]
    for repo in skills:
        lines.append(f"| {repo_link(repo)} | {md(lang(repo))} | {display_date(repo.get('pushedAt'))} | {md(repo.get('description') or '')} |")
    lines.extend(["", "## Suggested Maturity Tags", "", "| Tag | Meaning |", "|---|---|", "| `ready` | Stable enough to reuse as-is. |", "| `needs-demo` | Needs screenshots, examples, or README polish. |", "| `private` | Keep out of public hub unless intentionally published. |", ""])
    lines.extend(auto_update_section(config, stats))
    return "\n".join(lines)


def auto_update_section(config: dict, stats: dict) -> list[str]:
    lines = [
        "## Auto Update",
        "",
        "This repository is designed to refresh itself with GitHub Actions.",
        "",
        "- Schedule: daily, plus manual `workflow_dispatch`.",
        "- Data source: GitHub REST API.",
        "- Privacy default: public repositories only.",
        "- Private mode: set `META_INCLUDE_PRIVATE=true` and provide `META_GITHUB_TOKEN` only when the meta repository is private.",
        f"- Generated at: `{stats['generatedAt']}`.",
    ]
    if stats.get("privateOmitted"):
        lines.append(f"- Private repositories omitted from this public output: `{stats['privateOmitted']}`.")
    lines.append("")
    return lines


def render_readme(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]]) -> str:
    mode = config["mode"]
    if mode == "atlas":
        return render_atlas_readme(repos, config, stats, groups)
    if mode == "release":
        return render_release_readme(repos, config, stats)
    if mode == "pages":
        return render_pages_readme(repos, config, stats)
    if mode == "skills":
        return render_skills_readme(repos, config, stats)
    raise ValueError(f"unknown mode: {mode}")


def card(repo: dict) -> str:
    page = repo.get("pages", {}).get("url") or repo.get("homepageUrl") or repo["url"]
    image = repo.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/meta/{repo['nameWithOwner']}"
    desc = repo.get("description") or "No description yet."
    badges = []
    if repo.get("latestRelease"):
        badges.append("release")
    if is_skill(repo):
        badges.append("skill")
    badges.append(lang(repo))
    return f"""
      <article class="repo-card" data-kind="{html.escape(category(repo))}">
        <a class="shot" href="{html.escape(page)}"><img src="{html.escape(image)}" alt="{html.escape(repo['name'])} preview" loading="lazy"></a>
        <div class="repo-copy">
          <p class="kicker">{html.escape(" / ".join(badges))}</p>
          <h2><a href="{html.escape(page)}">{html.escape(repo['name'])}</a></h2>
          <p>{html.escape(desc)}</p>
          <div class="card-links">
            <a href="{html.escape(repo['url'])}">Repository</a>
            <a href="{html.escape(page)}">Live</a>
          </div>
        </div>
      </article>"""


def render_pages_site(repos: list[dict], config: dict, stats: dict) -> str:
    pages = sorted([repo for repo in repos if repo.get("pages", {}).get("enabled")], key=lambda item: item.get("pushedAt") or "", reverse=True)
    cards = "\n".join(card(repo) for repo in pages)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harzva Pages Hub</title>
  <link rel="preconnect" href="https://opengraph.githubassets.com">
  <style>
    :root {{
      --ink: #11110f;
      --paper: #f7f8f2;
      --line: #23231f;
      --acid: #d8ff3e;
      --coral: #ff5a3d;
      --cyan: #64d8c3;
      --mist: #e9ece5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        linear-gradient(90deg, rgba(17,17,15,.06) 1px, transparent 1px) 0 0 / 44px 44px,
        linear-gradient(rgba(17,17,15,.05) 1px, transparent 1px) 0 0 / 44px 44px,
        var(--paper);
      color: var(--ink);
      font-family: ui-serif, Georgia, "Times New Roman", serif;
    }}
    a {{ color: inherit; }}
    .hero {{
      min-height: 82vh;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      align-items: end;
      padding: 8vw 5vw 4vw;
      border-bottom: 2px solid var(--line);
      position: relative;
      overflow: hidden;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      width: min(62vw, 760px);
      aspect-ratio: 1;
      right: -18vw;
      top: -20vw;
      border: 2px solid var(--line);
      background: repeating-linear-gradient(135deg, var(--acid), var(--acid) 14px, transparent 14px, transparent 28px);
      transform: rotate(-8deg);
      z-index: 0;
    }}
    .hero-inner {{ position: relative; z-index: 1; max-width: 1180px; }}
    .eyebrow {{
      display: inline-flex;
      gap: 10px;
      align-items: center;
      font: 700 13px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      text-transform: uppercase;
      border: 2px solid var(--line);
      padding: 8px 10px;
      background: var(--cyan);
      box-shadow: 5px 5px 0 var(--line);
    }}
    h1 {{
      margin: 28px 0 14px;
      max-width: 980px;
      font-size: clamp(56px, 12vw, 168px);
      line-height: .82;
      letter-spacing: 0;
      font-weight: 900;
    }}
    .lead {{
      max-width: 760px;
      font-size: clamp(18px, 2.2vw, 30px);
      line-height: 1.18;
      margin: 0;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 34px;
      font: 700 14px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .stats span {{
      border: 2px solid var(--line);
      background: white;
      padding: 12px 14px;
      box-shadow: 4px 4px 0 var(--line);
    }}
    .gallery {{
      padding: 42px 5vw 80px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 18px;
    }}
    .repo-card {{
      border: 2px solid var(--line);
      background: white;
      box-shadow: 7px 7px 0 var(--line);
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 100%;
      transition: transform .18s ease, box-shadow .18s ease;
    }}
    .repo-card:hover {{
      transform: translate(-3px, -3px);
      box-shadow: 10px 10px 0 var(--coral);
    }}
    .shot {{ display: block; border-bottom: 2px solid var(--line); background: var(--mist); aspect-ratio: 1200 / 630; overflow: hidden; }}
    .shot img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .repo-copy {{ padding: 18px; display: flex; flex-direction: column; gap: 10px; }}
    .kicker {{ margin: 0; font: 700 12px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #4b4c44; text-transform: uppercase; }}
    h2 {{ margin: 0; font-size: 24px; line-height: 1.05; letter-spacing: 0; }}
    .repo-copy p:not(.kicker) {{ margin: 0; line-height: 1.42; font-size: 15px; }}
    .card-links {{ margin-top: auto; display: flex; gap: 10px; flex-wrap: wrap; }}
    .card-links a {{ font: 700 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-decoration: none; border-bottom: 2px solid var(--line); }}
    footer {{ padding: 24px 5vw 44px; font: 600 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    @media (max-width: 680px) {{
      .hero {{ min-height: 76vh; padding-top: 90px; }}
      .gallery {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="hero-inner">
        <div class="eyebrow">Harzva / GitHub Pages / Live Surface</div>
        <h1>Pages Hub</h1>
        <p class="lead">A public wall of live Harzva project sites, docs, demos, and experiment surfaces.</p>
        <div class="stats">
          <span>{stats['pages']} live pages</span>
          <span>{stats['publicRepositories']} public repos indexed</span>
          <span>daily refresh</span>
        </div>
      </div>
    </section>
    <section class="gallery" aria-label="GitHub Pages gallery">
      {cards}
    </section>
  </main>
  <footer>Generated {html.escape(stats['generatedAt'])}. Data source: GitHub REST API.</footer>
</body>
</html>"""


def render_atlas_site(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]]) -> str:
    rows = "\n".join(f"<li><strong>{html.escape(name)}</strong><span>{len(items)}</span></li>" for name, items in groups.items())
    featured = "\n".join(card(repo) for repo in repos[:9])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harzva Project Atlas</title>
  <style>
    :root {{ --ink:#171717; --paper:#fbfbf7; --leaf:#b7e35f; --red:#ee4938; --line:#171717; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font-family: ui-serif, Georgia, "Times New Roman", serif; }}
    header {{ min-height:78vh; display:grid; align-content:center; padding:8vw 6vw; border-bottom:2px solid var(--line); background:linear-gradient(115deg, var(--paper) 0 62%, var(--leaf) 62%); }}
    h1 {{ font-size:clamp(54px, 11vw, 150px); line-height:.86; letter-spacing:0; margin:0 0 20px; }}
    p {{ max-width:760px; font-size:22px; line-height:1.25; }}
    .stats {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:24px; }}
    .stats span, .map li {{ border:2px solid var(--line); background:white; padding:12px 14px; box-shadow:5px 5px 0 var(--line); }}
    .map {{ padding:42px 6vw; display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; list-style:none; margin:0; }}
    .map li {{ display:flex; justify-content:space-between; font-weight:800; }}
    .featured {{ padding:0 6vw 70px; display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; }}
    .repo-card {{ border:2px solid var(--line); background:white; box-shadow:6px 6px 0 var(--line); }}
    .shot {{ display:block; aspect-ratio:1200/630; overflow:hidden; border-bottom:2px solid var(--line); }}
    .shot img {{ width:100%; height:100%; object-fit:cover; }}
    .repo-copy {{ padding:16px; }}
    .kicker {{ font:700 12px ui-monospace,Menlo,monospace; text-transform:uppercase; }}
    h2 {{ margin:0; font-size:24px; line-height:1.05; }}
    .card-links {{ display:flex; gap:12px; font-weight:800; }}
  </style>
</head>
<body>
  <header>
    <h1>Harzva Project Atlas</h1>
    <p>One owner, many surfaces: repositories, releases, pages, skills, experiments, and forks gathered into a daily refreshed map.</p>
    <div class="stats"><span>{stats['publicRepositories']} public repositories</span><span>{stats['pages']} pages</span><span>{stats['releases']} releases</span><span>{stats['skills']} skills</span></div>
  </header>
  <ol class="map">{rows}</ol>
  <section class="featured">{featured}</section>
</body>
</html>"""


def write_docs(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]]) -> None:
    mode = config["mode"]
    if mode not in {"pages", "atlas"}:
        return
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    html_text = render_pages_site(repos, config, stats) if mode == "pages" else render_atlas_site(repos, config, stats, groups)
    (docs / "index.html").write_text(html_text, encoding="utf-8")
    if mode == "pages":
        pages = [repo for repo in repos if repo.get("pages", {}).get("enabled")]
        (docs / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Optional JSON source file relative to the repo root.")
    args = parser.parse_args()

    config = load_config()
    include_private = os.environ.get("META_INCLUDE_PRIVATE", str(config.get("includePrivate", False))).lower() == "true"
    repos = read_source(args.source) if args.source else fetch_repos(config["owner"], include_private)
    if not include_private:
        repos = [repo for repo in repos if not repo.get("isPrivate")]

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    stats = summary(repos, config)
    groups = grouped(repos)
    classified = {
        "summary": stats,
        "categories": {name: items for name, items in groups.items()},
        "pages": [repo for repo in repos if repo.get("pages", {}).get("enabled")],
        "releases": [repo for repo in repos if repo.get("latestRelease")],
        "skills": [repo for repo in repos if is_skill(repo)],
        "forks": [repo for repo in repos if repo.get("isFork")],
    }
    (data / "repos.json").write_text(json.dumps(repos, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "classified.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")

    mode = config["mode"]
    if mode == "release":
        (data / "releases.json").write_text(json.dumps(classified["releases"], ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == "pages":
        (data / "pages.json").write_text(json.dumps(classified["pages"], ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == "skills":
        (data / "skills.json").write_text(json.dumps(classified["skills"], ensure_ascii=False, indent=2), encoding="utf-8")

    (ROOT / "README.md").write_text(render_readme(repos, config, stats, groups), encoding="utf-8")
    write_docs(repos, config, stats, groups)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
