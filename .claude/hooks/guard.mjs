#!/usr/bin/env node
// Claude Code PreToolUse hook for Bash commands (Node, no dependencies; works on Windows/macOS/Linux).
//
// Blocks (exit code 2, reason on stderr):
//   1. `git commit` / `git push` when staged or outgoing changes contain likely secrets or files that
//      must never be committed. Uses gitleaks if it's installed; always also runs a built-in scan.
//   2. Installing or running browser-automation tools other than BrowserOS neo
//      (Playwright, Puppeteer, Selenium, browser-use, WebDriver), per the project's BrowserOS-only rule.
//
// Wire it up in .claude/settings.local.json (see docs/workspace-plan.md, Appendix B).
// Not a guarantee: GitHub push protection is the second line of defense.

import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function readStdin() {
  try {
    return JSON.parse(readFileSync(0, "utf8")); // Claude Code sends the hook input as JSON on stdin
  } catch {
    return {};
  }
}

function block(reason) {
  process.stderr.write(`BLOCKED by .claude/hooks/guard.mjs: ${reason}\n`);
  process.exit(2);
}

function git(args, cwd) {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  } catch {
    return "";
  }
}

// ---------- 2. BrowserOS-only rule ----------
// Only installs and runs are blocked; mentions (grep, npm ls, pip show, commit messages) are fine.
const TOOL = String.raw`(@playwright\/\S+|playwright|puppeteer(-core)?|selenium|browser[-_]use|webdriverio|webdriver|chromedriver|geckodriver|undetected[-_]chromedriver|pyppeteer)\b`;
const BROWSER_INSTALL_OR_RUN = [
  new RegExp(String.raw`\b(npm|pnpm|yarn|bun)\s+(i|install|add)\b[^;&|]*?\b` + TOOL, "i"),
  new RegExp(String.raw`\b(npx|pnpx|bunx)\s+(-\S+\s+)*` + TOOL, "i"),
  new RegExp(String.raw`\b(pip3?|pipx|poetry|conda|mamba)\s+(install|add)\b[^;&|]*?\b` + TOOL, "i"),
  new RegExp(String.raw`\buv\s+(add|pip\s+install|tool\s+(install|run)|run)\b[^;&|]*?\b` + TOOL, "i"),
  new RegExp(String.raw`\b(python3?|py)\s+(-\S+\s+)*-m\s+` + TOOL, "i"),
  new RegExp(String.raw`(^|[;&|]\s*)` + TOOL, "i"), // running the CLI directly, e.g. `playwright test`
];
// Remove quoted text (commit messages, echo strings) before matching.
const stripQuoted = (c) => c.replace(/"(?:[^"\\]|\\.)*"/g, '""').replace(/'[^']*'/g, "''");

// ---------- 1. secrets ----------
const SECRET_PATTERNS = [
  ["private key block", /-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----/],
  ["AWS access key", /\bAKIA[0-9A-Z]{16}\b/],
  ["GitHub token", /\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b/],
  ["Hugging Face token", /\bhf_[A-Za-z0-9]{30,}\b/],
  ["Anthropic key", /\bsk-ant-[A-Za-z0-9_-]{20,}/],
  ["OpenAI-style key", /\bsk-(proj-)?[A-Za-z0-9_-]{20,}/],
  ["NVIDIA API key", /\bnvapi-[A-Za-z0-9_-]{20,}/],
  ["Google API key", /\bAIza[0-9A-Za-z_-]{35}\b/],
  ["Slack token", /\bxox[abprs]-[A-Za-z0-9-]{10,}/],
  ["generic secret assignment", /\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*["']?[A-Za-z0-9_\-\/+=]{24,}["']?/i],
];
const FORBIDDEN_PATHS = [
  [/(^|\/)\.env$/, ".env file (only .env.example may be committed)"],
  [/(^|\/)\.env\.(?!example$)[^/]+$/, ".env.* file"],
  [/\.(pem|key|p12|pfx)$/i, "key/certificate file"],
  [/(^|\/)private\//, "private/ folder"],
  [/(^|\/)CLAUDE\.local\.md$/, "CLAUDE.local.md"],
  [/(^|\/)\.claude\/settings\.local\.json$/, ".claude/settings.local.json"],
  [/(^|\/)\.agent-logs\//, ".agent-logs/ (friction-log notes)"],
  [/(^|\/)data\/raw\//, "data/raw/ (raw datasets)"],
  [/\.(mp4|avi|mov|mkv)$/i, "video file (publish clips via a link, not in git)"],
  [/small_models_hack_reference/i, "confidential hackathon reference notes"],
];

function scanText(text) {
  const hits = [];
  for (const line of text.split("\n")) {
    if (!line.startsWith("+") || line.startsWith("+++")) continue; // only added lines
    for (const [name, re] of SECRET_PATTERNS) {
      if (re.test(line)) hits.push(name);
    }
  }
  return [...new Set(hits)];
}

function haveGitleaks() {
  const r = spawnSync("gitleaks", ["version"], { encoding: "utf8" });
  return r.status === 0;
}

function untrackedFiles(cwd) {
  return git(["ls-files", "-o", "--exclude-standard"], cwd).split("\n").filter(Boolean);
}

function contentAsAddedLines(cwd, file) {
  try {
    const buf = readFileSync(join(cwd, file));
    if (buf.length > 2 * 1024 * 1024 || buf.includes(0)) return ""; // skip big or binary files
    return buf.toString("utf8").split("\n").map((l) => "+" + l).join("\n");
  } catch {
    return "";
  }
}

function checkPaths(files, label) {
  for (const f of files) {
    for (const [re, why] of FORBIDDEN_PATHS) {
      if (re.test(f.replace(/\\/g, "/"))) block(`${label} "${f}" is a ${why}. Don't commit it.`);
    }
  }
}

function checkCommit(cwd, cmd, commitArgs) {
  // The hook runs BEFORE the command, so chained `git add ... && git commit` or `git commit -a`
  // would otherwise be scanned against an empty or stale index. Scan everything that could land.
  const chainedAdd = /\bgit\s+add\b/.test(cmd);
  const allFlag = /(^|\s)(-[a-zA-Z]*a[a-zA-Z]*|--all)\b/.test(commitArgs);
  const ranges = [["--cached"]];
  if (chainedAdd || allFlag) ranges.push(["HEAD"]);
  for (const r of ranges) {
    checkPaths(git(["diff", ...r, "--name-only", "--diff-filter=ACMR"], cwd).split("\n").filter(Boolean), "file");
    const hits = scanText(git(["diff", ...r, "-U0"], cwd));
    if (hits.length) block(`changes about to be committed look like they contain: ${hits.join(", ")}. Move the secret to .env (gitignored), then retry.`);
  }
  if (chainedAdd) {
    const untracked = untrackedFiles(cwd);
    checkPaths(untracked, "untracked file");
    for (const f of untracked) {
      const hits = scanText(contentAsAddedLines(cwd, f));
      if (hits.length) block(`untracked file "${f}" (would be added by git add) looks like it contains: ${hits.join(", ")}.`);
    }
  }
  if (haveGitleaks() && !chainedAdd && !allFlag) {
    const r = spawnSync("gitleaks", ["git", "--pre-commit", "--redact", "--staged", "--no-banner"], { cwd, encoding: "utf8" });
    if (r.status === 1) block(`gitleaks found a secret in staged changes:\n${(r.stdout || "") + (r.stderr || "")}`);
  }
}

function checkPush(cwd) {
  // Only the commits this push would send: current branch vs its upstream (or vs all remotes if none yet).
  const hasUpstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd).trim() !== "";
  const range = hasUpstream ? ["@{u}..HEAD"] : ["HEAD", "--not", "--remotes"];
  const hits = scanText(git(["log", "-p", "-U0", ...range], cwd));
  if (hits.length) block(`commits about to be pushed look like they contain: ${hits.join(", ")}. If a real secret was committed, ROTATE it at the provider first, then rewrite those commits.`);
  checkPaths(new Set(git(["log", "--name-only", "--format=", ...range], cwd).split("\n").filter(Boolean)), "a commit about to be pushed adds");
  if (haveGitleaks()) {
    const r = spawnSync("gitleaks", ["git", "--redact", "--no-banner", `--log-opts=${range.join(" ")}`], { cwd, encoding: "utf8" });
    if (r.status === 1) block(`gitleaks found a secret in commits about to be pushed:\n${(r.stdout || "") + (r.stderr || "")}`);
  }
}

const input = readStdin();
const cmd = String(input?.tool_input?.command ?? "");
const cwd = input?.cwd || process.cwd();
if (!cmd) {
  if (!input?.tool_name) process.stderr.write("guard.mjs: warning: no hook input received; checks skipped.\n");
  process.exit(0);
}

const unquoted = stripQuoted(cmd);
if (BROWSER_INSTALL_OR_RUN.some((re) => re.test(unquoted))) {
  block(
    "BrowserOS neo is the only allowed browser-automation tool in this project. " +
      "Don't install or run Playwright/Puppeteer/Selenium/browser-use/WebDriver. " +
      "Follow the BrowserOS failure procedure in CLAUDE.local.md: stop, report, ask Mina."
  );
}
const commit = unquoted.match(/\bgit\b[^|;&]*\bcommit\b([^|;&]*)/);
if (/\bgit\s+add\b[^;&|]*\s(-f|--force)\b/.test(unquoted)) {
  block("`git add -f` force-adds ignored files, and they're ignored for a reason (secrets, private notes, raw data). Remove -f.");
}
if (commit) checkCommit(cwd, unquoted, commit[1]);
if (/\bgit\b[^|;&]*\bpush\b/.test(unquoted)) checkPush(cwd);
process.exit(0);
