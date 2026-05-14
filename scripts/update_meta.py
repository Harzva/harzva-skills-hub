#!/usr/bin/env python3
"""Refresh a GitHub MetaRepo from live repository metadata."""

from __future__ import annotations

import argparse
import html
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_EXTENSIONS = (
    ".apk",
    ".aab",
    ".exe",
    ".msi",
    ".dmg",
    ".pkg",
    ".appimage",
    ".deb",
    ".rpm",
    ".ipa",
    ".zip",
    ".tar.gz",
    ".tgz",
    ".7z",
)


def load_config() -> dict:
    return json.loads((ROOT / "meta.config.json").read_text(encoding="utf-8"))


def token() -> str | None:
    return os.environ.get("META_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api_json(url: str, auth_token: str | None) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "metarepo-updater",
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
    primary_language = raw.get("primaryLanguage")
    if not isinstance(primary_language, dict):
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
        "openGraphImageUrl": raw.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/metarepo/{quote(full_name)}",
        "pages": raw.get("pages") or {"enabled": False},
        "latestRelease": raw.get("latestRelease"),
    }


def normalize_release(raw: dict | None) -> dict | None:
    if not raw:
        return None
    assets = []
    for asset in raw.get("assets") or []:
        assets.append(
            {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url") or asset.get("url"),
                "size": asset.get("size"),
                "downloadCount": asset.get("download_count", asset.get("downloadCount", 0)),
                "contentType": asset.get("content_type") or asset.get("contentType"),
            }
        )
    return {
        "name": raw.get("name") or raw.get("tag_name") or raw.get("tagName"),
        "tagName": raw.get("tag_name") or raw.get("tagName"),
        "url": raw.get("html_url") or raw.get("url"),
        "publishedAt": raw.get("published_at") or raw.get("publishedAt"),
        "prerelease": bool(raw.get("prerelease")),
        "draft": bool(raw.get("draft")),
        "assets": assets,
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
        repo["latestRelease"] = normalize_release(api_json(f"https://api.github.com/repos/{owner_name}/{repo_name}/releases/latest", auth_token))
    return sorted(repos, key=lambda item: (item["isFork"], item["nameWithOwner"].lower()))


def read_source(path: str | None) -> list[dict]:
    if not path:
        return []
    repos = json.loads((ROOT / path).read_text(encoding="utf-8-sig"))
    result = []
    for item in repos:
        repo = normalize_repo(item)
        repo["latestRelease"] = normalize_release(item.get("latestRelease"))
        result.append(repo)
    return result


def repo_text(repo: dict) -> str:
    topics = repo.get("repositoryTopics") or []
    topic_text = " ".join(str(topic) for topic in topics) if isinstance(topics, list) else str(topics)
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


def lang(repo: dict) -> str:
    return (repo.get("primaryLanguage") or {}).get("name") or "Mixed"


def category(repo: dict) -> str:
    text = repo_text(repo)
    language = lang(repo).lower()
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


def function_category(repo: dict, asset_name: str = "") -> str:
    text = f"{repo_text(repo)} {asset_name.lower()}"
    if repo.get("isFork"):
        return "Forked Downloads"
    if any(x in text for x in [".apk", ".aab", ".ipa", "android", "ios", "mobile", "flutter"]):
        return "Mobile Apps"
    if any(x in text for x in [".exe", ".msi", ".dmg", ".pkg", "desktop", "windows", "macos"]):
        return "Desktop Apps"
    if any(x in text for x in [".appimage", ".deb", ".rpm", "cli", "terminal", "linux", "rust", "shell"]):
        return "CLI and Infrastructure"
    if any(x in text for x in ["agent", "llm", "rag", "codex", "claude", "gpt"]):
        return "AI Agent Systems"
    if any(x in text for x in ["roadmap", "course", "learning", "knowledge", "tutorial"]):
        return "Learning and Knowledge"
    return "General Utilities"


def artifact_kind(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".apk"):
        return "Android APK"
    if lower.endswith(".aab"):
        return "Android Bundle"
    if lower.endswith(".ipa"):
        return "iOS IPA"
    if lower.endswith((".exe", ".msi")):
        return "Windows"
    if lower.endswith((".dmg", ".pkg")):
        return "macOS"
    if lower.endswith((".appimage", ".deb", ".rpm")):
        return "Linux"
    if lower.endswith((".zip", ".tar.gz", ".tgz", ".7z")):
        return "Archive"
    return "Release Asset"


def release_artifacts(repos: list[dict]) -> list[dict]:
    artifacts = []
    for repo in repos:
        release = repo.get("latestRelease")
        if not release:
            continue
        for asset in release.get("assets") or []:
            name = asset.get("name") or "asset"
            artifacts.append(
                {
                    "repo": repo["nameWithOwner"],
                    "repoName": repo["name"],
                    "repoUrl": repo["url"],
                    "description": repo.get("description"),
                    "language": lang(repo),
                    "assetName": name,
                    "assetUrl": asset.get("url"),
                    "size": asset.get("size"),
                    "downloadCount": asset.get("downloadCount", 0),
                    "kind": artifact_kind(name),
                    "functionCategory": function_category(repo, name),
                    "releaseName": release.get("name"),
                    "tagName": release.get("tagName"),
                    "releaseUrl": release.get("url"),
                    "publishedAt": release.get("publishedAt"),
                    "isFork": repo.get("isFork"),
                }
            )
    return sorted(artifacts, key=lambda item: (item["functionCategory"], item["repo"].lower(), item["assetName"].lower()))


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


def group_artifacts(artifacts: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for artifact in artifacts:
        groups.setdefault(artifact["functionCategory"], []).append(artifact)
    preferred = ["Mobile Apps", "Desktop Apps", "CLI and Infrastructure", "AI Agent Systems", "Learning and Knowledge", "General Utilities", "Forked Downloads"]
    return {name: sorted(groups[name], key=lambda item: item.get("publishedAt") or "", reverse=True) for name in preferred if name in groups}


def display_date(value: str | None) -> str:
    return (value or "")[:10]


def size_label(size: int | None) -> str:
    if not size:
        return ""
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return str(size)


def md(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def repo_link(repo: dict) -> str:
    return f"[{md(repo['name'])}]({repo['url']})"


def artifact_link(artifact: dict) -> str:
    return f"[{md(artifact['assetName'])}]({artifact['assetUrl']})"


def summary(repos: list[dict], config: dict, artifacts: list[dict]) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "owner": config["owner"],
        "mode": config["mode"],
        "publicRepositories": len([repo for repo in repos if not repo.get("isPrivate")]),
        "forks": len([repo for repo in repos if repo.get("isFork")]),
        "pages": len([repo for repo in repos if repo.get("pages", {}).get("enabled")]),
        "releases": len([repo for repo in repos if repo.get("latestRelease")]),
        "skills": len([repo for repo in repos if is_skill(repo)]),
        "artifacts": len(artifacts),
        "privateOmitted": config.get("privateOmitted", 0),
    }


def table_for_repos(repos: list[dict]) -> list[str]:
    lines = ["| Repository | Language | Stars | Forks | Updated | Description |", "|---|---:|---:|---:|---:|---|"]
    for repo in repos:
        lines.append(f"| {repo_link(repo)} | {md(lang(repo))} | {repo.get('stargazerCount', 0)} | {repo.get('forkCount', 0)} | {display_date(repo.get('pushedAt'))} | {md(repo.get('description') or '')} |")
    return lines


def table_for_artifacts(artifacts: list[dict]) -> list[str]:
    lines = ["| Download | Repo | Kind | Version | Size | Downloads | Published |", "|---|---|---:|---:|---:|---:|---:|"]
    for artifact in artifacts:
        lines.append(
            f"| {artifact_link(artifact)} | [{md(artifact['repoName'])}]({artifact['repoUrl']}) | {md(artifact['kind'])} | [{md(artifact.get('tagName'))}]({artifact.get('releaseUrl')}) | {size_label(artifact.get('size'))} | {artifact.get('downloadCount', 0)} | {display_date(artifact.get('publishedAt'))} |"
        )
    return lines


def auto_update_section(config: dict, stats: dict) -> list[str]:
    lines = [
        "## Auto Update",
        "",
        "This MetaRepo refreshes itself with GitHub Actions.",
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


def render_atlas_readme(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]], artifacts: list[dict]) -> str:
    hub_links = config["hubLinks"]
    artifact_groups = group_artifacts(artifacts)
    release_without_assets = [repo for repo in repos if repo.get("latestRelease") and not any(item["repo"] == repo["nameWithOwner"] for item in artifacts)]
    lines = [
        '<div align="center">',
        "",
        "# Harzva Project Atlas",
        "",
        "A download-first MetaRepo for Harzva: APK, EXE, desktop builds, CLI packages, release pages, and the hubs that explain the wider repository system.",
        "",
        f"[Live Atlas](https://{config['owner'].lower()}.github.io/harzva-project-atlas/) | [Release Hub]({hub_links['release']}) | [Pages Hub]({hub_links['pages']}) | [Skills Hub]({hub_links['skills']})",
        "",
        f"![Downloads](https://img.shields.io/badge/artifacts-{stats['artifacts']}-111111?style=for-the-badge) ![Releases](https://img.shields.io/badge/releases-{stats['releases']}-F05A28?style=for-the-badge) ![Pages](https://img.shields.io/badge/pages-{stats['pages']}-2D9CDB?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-6B8E23?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Download Map",
        "",
        "Downloads are grouped by repository function so APK, EXE, package, archive, and other release assets stay findable as Harzva adds or removes projects.",
        "",
    ]
    if artifact_groups:
        for name, items in artifact_groups.items():
            lines.extend([f"### {name}", ""])
            lines.extend(table_for_artifacts(items))
            lines.append("")
    else:
        lines.extend(["> No APK/EXE/package assets were detected in public latest releases yet.", ""])

    if release_without_assets:
        lines.extend(["## Release Pages Without Direct Assets", "", "| Repository | Latest release | Published | Description |", "|---|---:|---:|---|"])
        for repo in sorted(release_without_assets, key=lambda item: item["latestRelease"].get("publishedAt") or "", reverse=True):
            release = repo["latestRelease"]
            lines.append(f"| {repo_link(repo)} | [{md(release.get('tagName') or release.get('name'))}]({release.get('url')}) | {display_date(release.get('publishedAt'))} | {md(repo.get('description') or '')} |")
        lines.append("")

    lines.extend(
        [
            "## Meta Hubs",
            "",
            "| Hub | Purpose |",
            "|---|---|",
            f"| [harzva-release-hub]({hub_links['release']}) | Release-level details and version history. |",
            f"| [harzva-pages-hub]({hub_links['pages']}) | Visual gallery of GitHub Pages sites and demos. |",
            f"| [harzva-skills-hub]({hub_links['skills']}) | Codex skills and workflow recipes. |",
            "",
            "## Repository Categories",
            "",
            "| Category | Repositories |",
            "|---|---:|",
        ]
    )
    for name, items in groups.items():
        lines.append(f"| {name} | {len(items)} |")
    lines.append("")
    forks = groups.get("Forks", [])
    if forks:
        lines.extend(["## Forks", "", "Forked repositories are kept at the tail so Harzva-owned work and downloadable products remain easy to scan.", ""])
        lines.extend(table_for_repos(forks))
        lines.append("")
    lines.extend(auto_update_section(config, stats))
    return "\n".join(lines)


def render_release_readme(repos: list[dict], config: dict, stats: dict, artifacts: list[dict]) -> str:
    release_repos = sorted([repo for repo in repos if repo.get("latestRelease")], key=lambda item: item["latestRelease"].get("publishedAt") or "", reverse=True)
    lines = [
        '<div align="center">',
        "",
        "# Harzva Release Hub",
        "",
        "A living release board for Harzva projects with published GitHub releases, direct assets, and version entry points.",
        "",
        f"[Live Release Board](https://{config['owner'].lower()}.github.io/harzva-release-hub/) | [Project Atlas]({config['hubLinks']['atlas']})",
        "",
        f"![Releases](https://img.shields.io/badge/releases-{len(release_repos)}-F05A28?style=for-the-badge) ![Assets](https://img.shields.io/badge/assets-{stats['artifacts']}-111111?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-6B8E23?style=for-the-badge)",
        "",
        "</div>",
        "",
        "## Latest Releases",
        "",
        "| Project | Version | Assets | Published | Language | Description |",
        "|---|---:|---:|---:|---:|---|",
    ]
    artifacts_by_repo: dict[str, list[dict]] = {}
    for artifact in artifacts:
        artifacts_by_repo.setdefault(artifact["repo"], []).append(artifact)
    for repo in release_repos:
        release = repo["latestRelease"]
        asset_count = len(artifacts_by_repo.get(repo["nameWithOwner"], []))
        lines.append(f"| {repo_link(repo)} | [{md(release.get('tagName') or release.get('name'))}]({release.get('url')}) | {asset_count} | {display_date(release.get('publishedAt'))} | {md(lang(repo))} | {md(repo.get('description') or '')} |")
    if artifacts:
        lines.extend(["", "## Direct Download Assets", ""])
        lines.extend(table_for_artifacts(artifacts))
    lines.append("")
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
        f"[Open Gallery](https://{config['owner'].lower()}.github.io/harzva-pages-hub/) | [Project Atlas]({config['hubLinks']['atlas']})",
        "",
        f"![Pages](https://img.shields.io/badge/pages-{len(pages)}-2D9CDB?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-6B8E23?style=for-the-badge)",
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
        image = repo.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/metarepo/{repo['nameWithOwner']}"
        lines.append(f"| <img src=\"{image}\" width=\"260\" /> | [{md(repo['name'])}]({page_url}) | [{md(repo['nameWithOwner'])}]({repo['url']}) | {display_date(repo.get('pushedAt'))} |")
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
        f"[Live Skill Board](https://{config['owner'].lower()}.github.io/harzva-skills-hub/) | [Project Atlas]({config['hubLinks']['atlas']})",
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


def render_readme(repos: list[dict], config: dict, stats: dict, groups: dict[str, list[dict]], artifacts: list[dict]) -> str:
    mode = config["mode"]
    if mode == "atlas":
        return render_atlas_readme(repos, config, stats, groups, artifacts)
    if mode == "release":
        return render_release_readme(repos, config, stats, artifacts)
    if mode == "pages":
        return render_pages_readme(repos, config, stats)
    if mode == "skills":
        return render_skills_readme(repos, config, stats)
    raise ValueError(f"unknown mode: {mode}")


def stat_items(stats: dict) -> str:
    items = [
        ("repositories", stats["publicRepositories"]),
        ("artifacts", stats["artifacts"]),
        ("pages", stats["pages"]),
        ("releases", stats["releases"]),
        ("skills", stats["skills"]),
    ]
    return "\n".join(f'<span><strong>{value}</strong>{html.escape(label)}</span>' for label, value in items)


def page_shell(title: str, eyebrow: str, lead: str, stats_html: str, content_html: str, footer: str) -> str:
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      --ink: #161613;
      --paper: #f6f3ea;
      --panel: #fffdf6;
      --line: #22221d;
      --acid: #d7ff48;
      --coral: #ff6542;
      --cyan: #6bd8c7;
      --violet: #6f5cff;
      --muted: #5c5b53;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(22,22,19,.055) 1px, transparent 1px) 0 0 / 42px 42px,
        linear-gradient(rgba(22,22,19,.045) 1px, transparent 1px) 0 0 / 42px 42px,
        var(--paper);
      font-family: ui-serif, Georgia, "Times New Roman", serif;
    }
    a { color: inherit; }
    .hero {
      min-height: 76vh;
      display: grid;
      align-items: end;
      padding: 7vw 5vw 4vw;
      border-bottom: 2px solid var(--line);
      background: linear-gradient(112deg, transparent 0 62%, var(--acid) 62% 100%);
    }
    .eyebrow {
      display: inline-flex;
      width: fit-content;
      border: 2px solid var(--line);
      background: var(--cyan);
      box-shadow: 5px 5px 0 var(--line);
      padding: 8px 10px;
      font: 800 13px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      text-transform: uppercase;
    }
    h1 {
      margin: 28px 0 16px;
      max-width: 1100px;
      font-size: clamp(50px, 11vw, 154px);
      line-height: .84;
      letter-spacing: 0;
    }
    .lead { max-width: 860px; margin: 0; font-size: clamp(19px, 2.2vw, 30px); line-height: 1.18; }
    .stats { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 34px; }
    .stats span {
      min-width: 126px;
      border: 2px solid var(--line);
      background: var(--panel);
      box-shadow: 4px 4px 0 var(--line);
      padding: 12px 14px;
      font: 750 13px/1.1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      text-transform: uppercase;
    }
    .stats strong { display: block; font-size: 28px; font-family: Georgia, "Times New Roman", serif; }
    main { padding: 38px 5vw 70px; }
    .section-title { font-size: clamp(32px, 5vw, 76px); line-height: .92; margin: 24px 0 18px; letter-spacing: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
    .card {
      border: 2px solid var(--line);
      background: var(--panel);
      box-shadow: 7px 7px 0 var(--line);
      padding: 18px;
      min-height: 100%;
      transition: transform .18s ease, box-shadow .18s ease;
    }
    .card:hover { transform: translate(-3px, -3px); box-shadow: 10px 10px 0 var(--coral); }
    .shot { display: block; margin: -18px -18px 16px; border-bottom: 2px solid var(--line); aspect-ratio: 1200 / 630; overflow: hidden; background: #e9e6d9; }
    .shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .kicker { margin: 0 0 8px; color: var(--muted); font: 800 12px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-transform: uppercase; }
    h2 { margin: 0 0 10px; font-size: 25px; line-height: 1.05; letter-spacing: 0; }
    p { line-height: 1.42; }
    .links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .links a {
      text-decoration: none;
      border-bottom: 2px solid var(--line);
      font: 800 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .lane { margin-bottom: 34px; }
    footer { padding: 24px 5vw 44px; font: 650 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); }
    @media (max-width: 720px) {
      .hero { min-height: 68vh; padding-top: 78px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <section class="hero">
    <div>
      <div class="eyebrow">__EYEBROW__</div>
      <h1>__TITLE__</h1>
      <p class="lead">__LEAD__</p>
      <div class="stats">__STATS__</div>
    </div>
  </section>
  <main>__CONTENT__</main>
  <footer>__FOOTER__</footer>
</body>
</html>"""
    return (
        template.replace("__TITLE__", html.escape(title))
        .replace("__EYEBROW__", html.escape(eyebrow))
        .replace("__LEAD__", html.escape(lead))
        .replace("__STATS__", stats_html)
        .replace("__CONTENT__", content_html)
        .replace("__FOOTER__", html.escape(footer))
    )


def artifact_card(artifact: dict) -> str:
    desc = artifact.get("description") or "Release asset"
    return f'''<article class="card">
  <p class="kicker">{html.escape(artifact["kind"])} / {html.escape(artifact.get("tagName") or "")}</p>
  <h2>{html.escape(artifact["assetName"])}</h2>
  <p>{html.escape(desc)}</p>
  <p class="kicker">{html.escape(size_label(artifact.get("size")))} / {artifact.get("downloadCount", 0)} downloads / {html.escape(display_date(artifact.get("publishedAt")))}</p>
  <div class="links"><a href="{html.escape(artifact["assetUrl"] or "")}">Download</a><a href="{html.escape(artifact["repoUrl"])}">Repository</a><a href="{html.escape(artifact.get("releaseUrl") or artifact["repoUrl"])}">Release</a></div>
</article>'''


def repo_card(repo: dict, primary_url: str | None = None, label: str = "Repository") -> str:
    url = primary_url or repo.get("pages", {}).get("url") or repo.get("homepageUrl") or repo["url"]
    image = repo.get("openGraphImageUrl") or f"https://opengraph.githubassets.com/metarepo/{repo['nameWithOwner']}"
    desc = repo.get("description") or "No description yet."
    return f'''<article class="card">
  <a class="shot" href="{html.escape(url)}"><img src="{html.escape(image)}" alt="{html.escape(repo["name"])} preview" loading="lazy"></a>
  <p class="kicker">{html.escape(label)} / {html.escape(lang(repo))}</p>
  <h2>{html.escape(repo["name"])}</h2>
  <p>{html.escape(desc)}</p>
  <div class="links"><a href="{html.escape(url)}">{html.escape(label)}</a><a href="{html.escape(repo["url"])}">Code</a></div>
</article>'''


def render_atlas_site(repos: list[dict], config: dict, stats: dict, artifacts: list[dict]) -> str:
    chunks = []
    for name, items in group_artifacts(artifacts).items():
        cards = "\n".join(artifact_card(item) for item in items)
        chunks.append(f'<section class="lane"><h2 class="section-title">{html.escape(name)}</h2><div class="grid">{cards}</div></section>')
    if not chunks:
        chunks.append('<section class="lane"><h2 class="section-title">No Direct Assets Yet</h2><p>Latest releases were found, but no APK, EXE, package, or archive assets are attached yet.</p></section>')
    return page_shell(
        "Harzva Project Atlas",
        "Download map / APK / EXE / Packages",
        "A download-first MetaRepo that tracks release assets across Harzva repositories and groups them by function.",
        stat_items(stats),
        "\n".join(chunks),
        f"Generated {stats['generatedAt']}. Source: GitHub REST API.",
    )


def render_release_site(repos: list[dict], config: dict, stats: dict, artifacts: list[dict]) -> str:
    release_repos = sorted([repo for repo in repos if repo.get("latestRelease")], key=lambda item: item["latestRelease"].get("publishedAt") or "", reverse=True)
    cards = []
    for repo in release_repos:
        release = repo["latestRelease"]
        cards.append(repo_card(repo, release.get("url"), f"Release {release.get('tagName') or ''}"))
    content = f'<section class="lane"><h2 class="section-title">Latest Releases</h2><div class="grid">{"".join(cards)}</div></section>'
    if artifacts:
        content += f'<section class="lane"><h2 class="section-title">Direct Assets</h2><div class="grid">{"".join(artifact_card(item) for item in artifacts)}</div></section>'
    return page_shell("Harzva Release Hub", "Release board", "Latest versions, release pages, and downloadable assets in one living board.", stat_items(stats), content, f"Generated {stats['generatedAt']}.")


def render_pages_site(repos: list[dict], config: dict, stats: dict) -> str:
    pages = sorted([repo for repo in repos if repo.get("pages", {}).get("enabled")], key=lambda item: item.get("pushedAt") or "", reverse=True)
    cards = "\n".join(repo_card(repo, repo.get("pages", {}).get("url"), "Live Page") for repo in pages)
    content = f'<section class="lane"><h2 class="section-title">Live Pages</h2><div class="grid">{cards}</div></section>'
    return page_shell("Harzva Pages Hub", "Live sites / demos / docs", "A visual gallery for GitHub Pages surfaces published under Harzva.", stat_items(stats), content, f"Generated {stats['generatedAt']}.")


def render_skills_site(repos: list[dict], config: dict, stats: dict) -> str:
    skills = sorted([repo for repo in repos if is_skill(repo)], key=lambda item: item.get("pushedAt") or "", reverse=True)
    cards = "\n".join(repo_card(repo, repo["url"], "Skill") for repo in skills)
    content = f'<section class="lane"><h2 class="section-title">Skill Registry</h2><div class="grid">{cards}</div></section>'
    return page_shell("Harzva Skills Hub", "Codex skills / workflows", "A registry for Harzva skills, workflow skills, and reusable agent operating recipes.", stat_items(stats), content, f"Generated {stats['generatedAt']}.")


def write_docs(repos: list[dict], config: dict, stats: dict, artifacts: list[dict]) -> None:
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    mode = config["mode"]
    if mode == "atlas":
        html_text = render_atlas_site(repos, config, stats, artifacts)
    elif mode == "release":
        html_text = render_release_site(repos, config, stats, artifacts)
    elif mode == "pages":
        html_text = render_pages_site(repos, config, stats)
    elif mode == "skills":
        html_text = render_skills_site(repos, config, stats)
    else:
        raise ValueError(f"unknown mode: {mode}")
    (docs / "index.html").write_text(html_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Optional JSON source file relative to the repo root.")
    args = parser.parse_args()

    config = load_config()
    include_private = os.environ.get("META_INCLUDE_PRIVATE", str(config.get("includePrivate", False))).lower() == "true"
    repos = read_source(args.source) if args.source else fetch_repos(config["owner"], include_private)
    if not include_private:
        repos = [repo for repo in repos if not repo.get("isPrivate")]

    artifacts = release_artifacts(repos)
    stats = summary(repos, config, artifacts)
    groups = grouped(repos)
    classified = {
        "summary": stats,
        "categories": {name: items for name, items in groups.items()},
        "artifacts": artifacts,
        "artifactCategories": group_artifacts(artifacts),
        "pages": [repo for repo in repos if repo.get("pages", {}).get("enabled")],
        "releases": [repo for repo in repos if repo.get("latestRelease")],
        "skills": [repo for repo in repos if is_skill(repo)],
        "forks": [repo for repo in repos if repo.get("isFork")],
    }

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    (data / "repos.json").write_text(json.dumps(repos, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "classified.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "artifacts.json").write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8")

    mode = config["mode"]
    if mode == "release":
        (data / "releases.json").write_text(json.dumps(classified["releases"], ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == "pages":
        (data / "pages.json").write_text(json.dumps(classified["pages"], ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == "skills":
        (data / "skills.json").write_text(json.dumps(classified["skills"], ensure_ascii=False, indent=2), encoding="utf-8")

    (ROOT / "README.md").write_text(render_readme(repos, config, stats, groups, artifacts), encoding="utf-8")
    write_docs(repos, config, stats, artifacts)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
