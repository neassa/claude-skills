---
name: atypon-grafana-site-health
description: >-
  Use when checking Atypon site or Literatum health, availability, HTTP traffic,
  errors, or service metrics through the atypon-grafana MCP.
---

# Checking Atypon site health in Grafana

## Workflow

1. Discover the Prometheus datasource named for the site (for APS, `mimir-aps`) and
   inspect its active labels. Do not assume dashboard search or the assertions endpoint
   is available; confirm the relevant data source and metrics directly.
2. Resolve the exact `service_name` and `env` before querying. APS has distinct
   services/environments, including `aps_A27_literatum` (`literatum` production),
   `aps_A27_staging` (`staging`), and `aps_A8_midtierbeta` (`midtierbeta`). Never
   combine them when reporting production health.
3. Check recent request traffic and response codes over a short window. This telemetry
   uses a native histogram named `http_server_request_duration`, not the classic
   `_count` series. A PromQL-compatible query is:

   ```promql
   sum by (http_response_status_code) (
     histogram_count(rate(http_server_request_duration{
       service_name="aps_A27_literatum", env="literatum"
     }[5m]))
   )
   ```

   To isolate server errors, add
   `http_response_status_code=~"5.."` inside the selector. Break down by `instance`
   when locating which web nodes return errors. Use the Grafana MCP's Prometheus query
   tool where available; if using the Grafana API, encode the PromQL as the `query`
   parameter and use an instant query.
4. Report the sample timestamp and timezone, request rates, status codes, and instances.
   Treat nonzero recent 2xx traffic as evidence that the application is responding, not
   as proof of end-to-end public availability. For that, use a verified synthetic
   check. Empty results mean unknown/no matching telemetry, not healthy.

## Pitfalls

- Do not query `http_server_request_duration_count`: this deployment exposes a native
  histogram, so that classic counter name returns no series.
- Do not use an absent `up{job="aps_A27_literatum"}` series as evidence the site is
  down; first verify the datasource's actual metrics and instrumentation.
- Prometheus label-value discovery may return labels beyond the requested recent
  window. Verify recency with an instant/range metric query.
- The `get_assertions` call returned `Plugin not found` in the 2026-10-31 check; do not
  infer site health from that endpoint failure.

## Founding failure

On 2026-10-31, searching dashboards for `APS` returned unrelated dashboards and the
assertions call failed. Inspecting `mimir-aps` revealed three APS service/environment
variants and a native HTTP histogram; classic `_count` and `up` queries returned no
series. The cheapest reliable check is to resolve the production labels, then query
`histogram_count(rate(http_server_request_duration{...}[5m]))` and report its timestamp
and limitations.
