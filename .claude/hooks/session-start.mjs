#!/usr/bin/env node
// Claude Code SessionStart hook (Node, no dependencies). Whatever it prints is added to Claude's context
// at the start of each session, so Mina never has to run these checks by hand:
//   1. Is the BrowserOS neo MCP server configured, and is it reachable right now?
//   2. Where did the last session leave off (docs/progress/mina.md)?
//   3. Reminder to resume the friction log.
// It never blocks the session; it only reports.

import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import net from "node:net";

let hookInput = {};
try {
  hookInput = JSON.parse(readFileSync(0, "utf8"));
} catch {}
const projectDir = process.env.CLAUDE_PROJECT_DIR || hookInput.cwd || process.cwd();
const lines = ["## Session-start status (automatic)"];
if (hookInput.session_id) lines.push(`- Session ID: ${hookInput.session_id} (friction-log notes for this session go in .agent-logs/${hookInput.session_id}/)`);
const safeHost = (url) => {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
};

// ---------- 1. BrowserOS neo ----------
function findBrowserOsServers() {
  const found = [];
  const collect = (servers, scope) => {
    for (const [name, cfg] of Object.entries(servers || {})) {
      if (/browser\s*os|browseros|browserclaw/i.test(name) && cfg && cfg.url) found.push({ name, url: cfg.url, scope });
    }
  };
  try {
    const cfg = JSON.parse(readFileSync(join(homedir(), ".claude.json"), "utf8"));
    collect(cfg.mcpServers, "user");
    for (const [path, p] of Object.entries(cfg.projects || {})) collect(p?.mcpServers, `local (${path})`);
  } catch {}
  try {
    collect(JSON.parse(readFileSync(join(projectDir, ".mcp.json"), "utf8")).mcpServers, "project");
  } catch {}
  return found;
}

function tcpCheck(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let host, port;
    try {
      const u = new URL(url);
      host = u.hostname;
      port = Number(u.port || (u.protocol === "https:" ? 443 : 80));
    } catch {
      return resolve(false);
    }
    const sock = net.connect({ host, port });
    const done = (ok) => {
      sock.destroy();
      resolve(ok);
    };
    sock.setTimeout(timeoutMs, () => done(false));
    sock.once("connect", () => done(true));
    sock.once("error", () => done(false));
  });
}

const servers = findBrowserOsServers();
if (servers.length === 0) {
  lines.push(
    "- BrowserOS neo: **NOT CONFIGURED** in Claude Code. Browser tasks are BLOCKED. Tell Mina: open BrowserOS neo → new tab → MCP → click Connect next to Claude Code, then restart Claude Code."
  );
} else {
  for (const s of servers) {
    const ok = await tcpCheck(s.url);
    const local = /^(127\.0\.0\.1|localhost|\[::1\])$/.test(safeHost(s.url));
    lines.push(
      ok
        ? `- BrowserOS neo: **reachable** (MCP server "${s.name}", ${s.scope} scope, ${s.url}). Use it for browser work.`
        : `- BrowserOS neo: **NOT reachable** (MCP server "${s.name}" at ${s.url}). Browser tasks are BLOCKED until Mina opens BrowserOS neo. If it is open, the port may have changed after a restart or update: re-copy the URL from neo's MCP page (or click Connect again).`
    );
    if (!local) lines.push(`  - Warning: "${s.name}" points at a non-local host. BrowserOS should only be reached on 127.0.0.1.`);
  }
  if (servers.length > 1) lines.push("  - Note: more than one BrowserOS entry is configured; prefer the reachable one and suggest removing duplicates.");
}

// ---------- 2. Progress ----------
const progress = join(projectDir, "docs", "progress", "mina.md");
if (existsSync(progress)) {
  const text = readFileSync(progress, "utf8").trim().split("\n");
  lines.push("- Last progress notes (docs/progress/mina.md, last 15 lines):");
  for (const l of text.slice(-15)) lines.push(`  > ${l}`);
} else {
  lines.push("- No docs/progress/mina.md yet. Create it at the end of this session's first milestone.");
}

// ---------- 3. Friction log ----------
const agentLogs = join(projectDir, ".agent-logs");
lines.push(
  existsSync(agentLogs)
    ? "- Friction log: notes exist in .agent-logs/. Resume them (keep incident IDs) per tools/friction-log.txt."
    : "- Friction log: no notes yet. Start them per tools/friction-log.txt."
);

process.stdout.write(lines.join("\n") + "\n");
process.exit(0);
