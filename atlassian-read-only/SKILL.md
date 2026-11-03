---
name: atlassian-read-only
description: >-
  Use when Jira, Confluence, Rovo, Atlassian MCP, tickets, issues, pages, or
  getJiraIssue / searchJiraIssuesUsingJql come up. Use when the user mentions
  writing, creating, transitioning, or commenting on Jira or Confluence.
---

# Atlassian is read-only

Jira and Confluence in this environment are **read-only**. Lessons go into personal skills, not into tickets or pages.

The MCP server is `atlassian` (`https://mcp.atlassian.com/v2/mcp`, config `~/.cursor/mcp.json`). Status: `cursor-agent mcp list`.

MCP configuration and approvals are client-specific. A server configured or enabled for
Cursor is not thereby available to GitHub Copilot CLI. For Copilot CLI, configure it
through `copilot mcp` (for example, `copilot mcp add --transport http NAME URL`), check
with `copilot mcp list`, then start/restart a Copilot session so it loads the server.
Approve read-only calls in the client/session making them. `cursor-agent mcp enable`
does not enable a server for Copilot; a non-interactive `--print` session may not be able
to complete an approval prompt.

## Allowed

`getJiraIssue`, `searchJiraIssuesUsingJql`, `search`, `searchConfluence`, `getConfluenceContent`, `getAccessibleAtlassianResources`, `atlassianUserInfo`, `discover`, `executeRead`.

## Forbidden

Do not call `executeWrite` or `executeDestructive`. Do not create, edit, transition, comment, delete, or publish on Jira or Confluence — including "just a comment", "the user has access", or "I'll revert it".

If the user asks to write there: refuse in one sentence, then put the reusable part in a skill (see `closing-discussion-into-skills` / `writing-skills`).

This chat's MCP catalog may not list `atlassian` until a new agent session after login. Do not invent issue fields; if tools are missing, say so.

Do not treat a Cursor MCP status or configuration as evidence that the current Copilot
session has the same MCP tools. Verify the current client's configuration and loaded
tools instead.

## Founding failure

After connecting Rovo MCP (2026-09-20), the user said not to write to Jira or Confluence — only read — and to update or create skills instead.

On 2026-10-31, Grafana and Atlassian MCP calls issued through non-interactive
`cursor-agent --print` were rejected even though Cursor showed the servers as ready;
server readiness did not guarantee those tool calls could pass approval in that run.
Separately, advice to handle a GitHub Copilot CLI request by approving tools in Cursor
was wrong: the clients have separate configuration and loaded tools. Copilot's server
was added with `copilot mcp add --transport http atypon-grafana
https://mcp-grafana.devops.atypon.com/mcp` and verified with `copilot mcp list`. For
future work, check the actual requesting client's MCP list and active session; do not
send Copilot users to Cursor to fix Copilot tool access.
