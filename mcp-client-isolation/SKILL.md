---
name: mcp-client-isolation
description: >-
  Use when an MCP server works in one AI client but not another, when configuring
  Cursor or GitHub Copilot CLI MCP servers, or when MCP calls are rejected despite
  the server appearing ready.
---

# MCP client isolation

MCP configuration, loaded tools, authentication, and approval state belong to a client
and often to a session. A server being configured or "ready" in Cursor does not make it
available to GitHub Copilot CLI, and enabling it in one client does not approve calls
in another.

## What to do

- Identify the client actually making the request. Check that client's server list and
  current session's loaded tools before retrying.
- Cursor Agent uses its own MCP configuration (`~/.cursor/mcp.json`) and
  `cursor-agent mcp list` / `cursor-agent mcp enable NAME`.
- GitHub Copilot CLI uses `copilot mcp` and user configuration. Add a remote HTTP
  server with `copilot mcp add --transport http NAME URL`; verify with
  `copilot mcp list`. Start or restart the Copilot session to load the new server.
- Approve the specific tool calls in the same interactive client/session that will
  execute them. A non-interactive print/script mode may not be able to complete a
  prompted approval. Do not compensate by granting blanket tool permissions.
- If a call is rejected, report the rejection accurately; do not claim the server is
  unavailable or keep retrying as if the call succeeded.

## Founding failure

On 2026-10-31, Grafana and Atlassian calls from non-interactive `cursor-agent --print`
were rejected although Cursor listed its servers as ready; ready did not mean those
calls could complete approval in that run. Separately, advice to fix Copilot CLI access
by approving tools in Cursor was incorrect because their configs and loaded tools are
independent. `copilot mcp add --transport http atypon-grafana
https://mcp-grafana.devops.atypon.com/mcp` registered the server for Copilot, and
`copilot mcp list` verified it. Check the client actually making the request and do not
redirect Copilot users to Cursor for Copilot configuration or approval.
