---
name: debugging-atypon-puppet-agent-certs
description: >-
  Use when puppet agent runs fail on Atypon hosts or dev laptops with certificate errors —
  "certificate verify failed", "unable to get local issuer certificate for
  CN=puppet.int.atypon.com", endless "Info: Refreshing CA certificate" — or when ssh to
  *.int.atypon.com fails with "failed to connect to local proxy: Connection refused" /
  "kex_exchange_identification: Connection closed". Also when someone asks how to
  clear/clean/revoke a puppet agent certificate at Atypon.
---

# Debugging Atypon Puppet Agent Cert Failures

## Overview

Atypon runs three puppet servers — `puppet.int.atypon.com` (DC), `puppet.atypon.com` (Santa Clara), `puppet.gcp.atypon.com` (GCP) — with agents on all servers **and developer Linux machines**, run every 2h by cron via `/etc/puppetlabs/puppet/puppetagent.sh` (source: github.com/atypon/puppet-control, `site-modules/atypon_host/templates/puppetagent.sh.erb`).

**Core principle:** a cert verify failure paired with any local-proxy/ssh failure means the machine is off the tunnel — fix connectivity (Cloudflare WARP) before touching certificates. Cleaning certs while off-tunnel re-fails identically and the cleaner endpoints are internal-only.

## Recognize the signature

| Observation | Meaning |
|---|---|
| `certificate verify failed [unable to get local issuer certificate for CN=puppet...]` AND ssh shows `failed to connect to local proxy: [111] Connection refused` | WARP daemon down / disconnected. TLS is likely hitting an interception proxy presenting a forged cert. Fix WARP, not puppet. |
| Same cert error but WARP up and `openssl s_client` shows the real Puppet CA as issuer | Stale local CA (rotated CA, old `ca.pem`). Clean certs (below). |
| `openssl s_client` shows a corporate/Zscaler-style issuer | Interception path — machine is not routing via the tunnel. Never add the interception root to puppet's trust. |
| `kex_exchange_identification: Connection closed ... UNKNOWN port 65535` | Downstream corpse of the dead ProxyCommand, not a server-side problem. |

## Diagnostic order

```bash
warp-cli status                     # reconnect: warp-cli connect; or sudo systemctl restart warp-svc
ssh -G <host> | grep -iE 'proxy|jump'   # what local proxy ssh expects; ss -ltnp to see if it listens
echo | openssl s_client -connect puppet.int.atypon.com:8140 \
  -servername puppet.int.atypon.com 2>/dev/null | openssl x509 -noout -issuer -subject
sudo puppet ssl verify              # does local CA bundle verify the server?
```

## Clearing the agent certificate

Atypon's sanctioned way — the agent wrapper's `-c` flag (also does the server-side revoke):

```bash
sudo /etc/puppetlabs/puppet/puppetagent.sh -c   # rm -rf ssl dir + revoke+DELETE cert on CA
sudo puppet agent -tv                            # re-bootstrap fresh cert
```

It downloads a "puppetcleaner" client cert from `http://puppet/cleaner/` and calls `puppet-ca/v1/certificate_status/<certname>` (PUT revoked, then DELETE) — internal-only, so it requires the tunnel.

Native equivalents (local side only — no server revoke):

```bash
sudo puppet ssl clean               # Puppet 6+; the "close to puppet agent -tv" command
sudo puppet ssl bootstrap           # re-request + wait for signing
sudo rm -rf $(puppet config print ssldir)   # if clean leaves stale ca.pem behind
# server side: sudo puppetserver ca clean --certname <fqdn>   (old: puppet cert clean <fqdn>)
```

## Common mistakes

- Cleaning certs while off-tunnel — same verify error returns and cleaner URLs are unreachable.
- Reading the CN in the error as proof the right server answered — an interception proxy forges the same CN; only the **issuer** distinguishes them.
- Assuming `puppet ssl clean` refreshed the CA — it may keep the cached `ca.pem`; remove the whole ssldir if the CA rotated.
- Blaming the remote sshd for `kex_exchange_identification` when the local ProxyCommand died first.
