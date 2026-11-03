---
name: literatum-solr-health
description: >-
  Use when checking or reporting live Literatum SolrCloud health by site and
  environment, mapping products to Solr/ZooKeeper in deployconf, or explaining
  Solr ZooKeeper status and overseer queues.
---

# Literatum Solr health (read-only)

Use for live status reports, not deployment or recovery. Keep all remote checks read-only;
never restart containers, change ZooKeeper configuration, or run Ansible/deploy actions.

## Verify the target and topology

1. Establish the exact site and environment. Do not infer production/non-production from
   a host name or an old conversation.
2. Read the matching environment's deployconf product row for Solr hosts and ZooKeeper
   cluster. Treat deployconf and skill snapshots as mapping evidence, not live truth.
3. If repository content may be stale, consult the current read-only checkout. Do not read
   secrets; use the Literatum safe-view process for secret-bearing files.
4. On a Solr node, use `docker ps` to identify the site's Solr container. Exclude exporter
   containers from Solr-node counts.
5. A multi-host Solr cluster can be inspected through one reachable node's read-only
   Collections API; confirm its `live_nodes` response rather than counting containers on
   only one Docker host.

## SSH and tunnel boundary

- Use the user's approved route or jump host only when the user asks for live inspection.
  `sshuttle` routes specified local CIDRs through an SSH jump host; it is a network tunnel,
  not a Solr health check. Do not start it automatically.
- Keep SSH host-key checking enabled. If a target key is unknown, stop and request a
  trusted fingerprint or have the user provision `known_hosts`; do not silently trust a
  new key or disable verification.
- State the exact target, environment, commands/data sources, and read-only scope.

## Read-only health evidence

Collect a compact set of facts from Solr:

- `/admin/info/system`: SolrCloud mode and Solr version.
- `/admin/collections?action=CLUSTERSTATUS`: live nodes, collections, shard health,
  replica state and placement, and aliases.
- `/admin/collections?action=OVERSEERSTATUS`: leader and queue sizes.
- `/admin/zookeeper/status`: Solr's ZooKeeper view, ensemble size, connection string,
  and diagnostic errors.
- Optional `q=*:*&rows=0` collection queries: document counts, when useful or requested.
- For ambiguous ZooKeeper status, probe each exact `host:port` from Solr's reported
  connection string with read-only `srvr`. Compare peer responses for one leader, followers,
  matching zxid, and node counts. `srvr` success demonstrates peer reachability; it does not
  replace a formal quorum or application-level test.

## Interpret ZooKeeper red correctly

`/admin/zookeeper/status` may report RED because the `conf` four-letter command is not
whitelisted. That is a diagnostic/API limitation, not by itself proof that ZooKeeper is
unreachable or lacks quorum. Report separately:

1. Solr's ZooKeeper diagnostic status and the exact error.
2. Direct `srvr` evidence from the configured peers.
3. Solr's own evidence: live nodes, overseer, and active/healthy shards and replicas.

Do not label ZooKeeper healthy solely because collections are GREEN; state what each signal
proves and what remains unverified. Do not change `zoo.cfg` or the four-letter-command
whitelist as part of a status check.

## Overseer queues

Report the three values in this order: `overseer_queue_size`,
`overseer_work_queue_size`, `overseer_collection_queue_size`. The leader is the elected
cluster coordinator. A small nonzero queue snapshot is not by itself an incident; trend or
repeat the read-only check before treating persistent/growing backlog as a problem.

## Report format

Always return a concise report, not only a status word:

- Overall assessment, environment, and observation time.
- Solr version, live node count/names, collection health, and unhealthy shard/replica detail.
- ZooKeeper diagnostic status versus peer evidence, with limitations.
- Overseer leader and queues.
- Aliases and document counts when requested or useful; omit verbose raw JSON.
- Clearly label live observations versus deployconf/repository mapping. Do not imply this is
  an end-to-end website availability test.

## Dated examples and founding lesson

On 2026-10-31, staging deployconf mapped APS to `literatum-stag-solr1`, ZooKeeper cluster
`stag-zk-4` on port 2024, and CABI to `literatum7/4/3-stag-solr1`, cluster `stag-zk-1` on
port 1734. The live Solr-reported CABI string used `stag-zk-1-{1,2,3}:1734/staging-cabi`;
the APS string used those same host names on port 2024 with `/staging-aps`. For both sites,
all configured peers answered `srvr` as one leader and two followers with matching zxid and
node count, while Solr's ZooKeeper endpoint returned RED because `conf` was not whitelisted.
All observed collections were GREEN and overseer queues were `0 / 0 / 2`.

The initial interpretation risk was treating Solr's RED as ZooKeeper failure and assuming
the deployconf mapping alone described live topology. The cheapest correction was to read
the exact runtime `zkHost`, compare it to deployconf, probe each configured peer with
`srvr`, and inspect Solr's live-node/replica state.
