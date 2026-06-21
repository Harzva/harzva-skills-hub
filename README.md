<div align="center">

# Harzva Skills Hub

A registry of Harzva Codex skills, workflow skills, and agent operating recipes.

[Live Skill Board](https://harzva.github.io/harzva-skills-hub/) | [Project Atlas](https://github.com/Harzva/harzva-project-atlas)

![Skills](https://img.shields.io/badge/skills-27-6B8E23?style=for-the-badge) ![Auto Update](https://img.shields.io/badge/update-daily-111111?style=for-the-badge)

</div>

## Skill Registry

| Skill Repository | Language | Updated | Description |
|---|---:|---:|---|
| [chatgpt2localbridge](https://github.com/Harzva/chatgpt2localbridge) | TypeScript | 2026-06-21 | Codex/ChatGPT plugin app and OAuth MCP connector for approved local workspaces. |
| [harzva-skills-hub](https://github.com/Harzva/harzva-skills-hub) | Python | 2026-06-20 | Auto-updating GitHub Pages registry of Harzva Codex skills, workflow skills, and agent recipes. |
| [mcp-skills-hub](https://github.com/Harzva/mcp-skills-hub) | TypeScript | 2026-06-19 | MCP Skills Hub - 汇集50+ Model Context Protocol Skill与Server |
| [pami-skill-suites](https://github.com/Harzva/pami-skill-suites) | Python | 2026-06-18 | Context-safe IEEE and Elsevier journal manuscript skill suites with metadata-only RAG trace assets |
| [CampusAgent-QA](https://github.com/Harzva/CampusAgent-QA) | Java | 2026-06-16 | Agentic campus QA system with RAG retrieval, LLM Wiki memory, and GBrain skills |
| [rebuttal-skill-suite](https://github.com/Harzva/rebuttal-skill-suite) | Python | 2026-06-04 | Automated gates and reviewer-aware workflows for safer academic rebuttals. |
| [AgentWorkOS](https://github.com/Harzva/AgentWorkOS) | Python | 2026-06-04 | Package-managed operating layer for AI agent workspaces: scan, lock, sync, doctor, and install agent context. |
| [xhs-skill-suite](https://github.com/Harzva/xhs-skill-suite) | Mixed | 2026-06-04 | Public-safe Xiaohongshu skill suite for GitHub and AI-tool promotion workflows. |
| [deepseek-cli](https://github.com/Harzva/deepseek-cli) | JavaScript | 2026-05-28 | DeepSeek-first API CLI and Agent Skills toolkit with multi-provider fallback |
| [gh-repo-cartographer](https://github.com/Harzva/gh-repo-cartographer) | Python | 2026-05-18 | Codex skill and CLI for mapping GitHub repositories to local checkouts and sync status. |
| [Project2AgentWorkOS](https://github.com/Harzva/Project2AgentWorkOS) | HTML | 2026-05-16 | Transfer all projects, Codex threads, failure reviews, and half-finished ideas into AgentWorkOS: Agents, Memory, Skills, MCP, Workflow, and Rules. |
| [github-repo-scout](https://github.com/Harzva/github-repo-scout) | PowerShell | 2026-05-14 | Codex skill for searching GitHub repos and archiving useful repo cards |
| [build-your-meta-repo-skill](https://github.com/Harzva/build-your-meta-repo-skill) | Python | 2026-05-14 | Codex skill for building auto-updating GitHub MetaRepos: artifact atlas, release hub, Pages hub, and skills hub. |
| [design-md-flow](https://github.com/Harzva/design-md-flow) | Python | 2026-05-14 | Portable DESIGN.md workflow skill for agent-driven frontend design |
| [android-release-emulator-qa-skill](https://github.com/Harzva/android-release-emulator-qa-skill) | Python | 2026-05-14 | Codex skill for Android release APK QA with emulator, adb, screenshots, UI XML, logcat, SHA256, and GitHub Release artifact checks. |
| [github-management-suite](https://github.com/Harzva/github-management-suite) | Python | 2026-05-14 | Cross-platform Codex skill for full GitHub repository lifecycle management |
| [ReadmeShowcaseScreenshot-Skill](https://github.com/Harzva/ReadmeShowcaseScreenshot-Skill) | JavaScript | 2026-05-14 | Codex skill for README-ready screenshots, GIFs, videos, hero images, and preview galleries. |
| [gh-actions-release-builder](https://github.com/Harzva/gh-actions-release-builder) | Mixed | 2026-05-13 | Codex skill for professional GitHub Actions build, package, artifact, and release workflows |
| [gh-account-router](https://github.com/Harzva/gh-account-router) | Python | 2026-05-12 | Codex skill and CLI helper for routing gh commands across GitHub accounts |
| [image2_UI_skill](https://github.com/Harzva/image2_UI_skill) | Mixed | 2026-05-12 |  |
| [everything-agent-cli-to-claude-code](https://github.com/Harzva/everything-agent-cli-to-claude-code) | Shell | 2026-04-23 | Umbrella repo for agent CLI to Claude Code adapters, templates, and plugin registry. |
| [Oh-Reflective-loop-skills](https://github.com/Harzva/Oh-Reflective-loop-skills) | Mixed | 2026-04-23 |  |
| [gen-zhihu-article-skill](https://github.com/Harzva/gen-zhihu-article-skill) | Mixed | 2026-04-11 |  |
| [zhihu-publish-skill](https://github.com/Harzva/zhihu-publish-skill) | Mixed | 2026-04-11 |  |
| [webpage-screenshot-md-skill](https://github.com/Harzva/webpage-screenshot-md-skill) | JavaScript | 2026-04-10 |  |
| [loloop-skill](https://github.com/Harzva/loloop-skill) | Mixed | 2026-04-10 |  |
| [copilot-plugin-cc](https://github.com/Harzva/copilot-plugin-cc) | Shell | 2026-04-07 | copilot-plugin-cc placeholder repository for Claude Code adapter work. |

## Suggested Maturity Tags

| Tag | Meaning |
|---|---|
| `ready` | Stable enough to reuse as-is. |
| `needs-demo` | Needs screenshots, examples, or README polish. |
| `private` | Keep out of public hub unless intentionally published. |

## Auto Update

This MetaRepo refreshes itself with GitHub Actions.

- Schedule: daily, plus manual `workflow_dispatch`.
- Data source: GitHub REST API.
- Privacy default: public repositories only.
- Private mode: set `META_INCLUDE_PRIVATE=true` and provide `META_GITHUB_TOKEN` only when the meta repository is private.
- Generated at: `2026-06-21T08:10:50.464573+00:00`.
- Private repositories omitted from this public output: `13`.
