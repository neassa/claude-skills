# 30 — atypon/rd_jobs: the Rundeck jobs behind the Deploy Server's Rundeck actions

Read 2026-09-26, read-only. Every branch was fetched `--depth 1` and extracted with `git archive FETCH_HEAD` into `$LIT_REPOS/rd_jobs-branches/<branch>/`. All files were read with `tools/safe_view.py` (masked). Other repos read at: `deployserver` @ `b726c83`, `opstool` master @ `4562351`, `k8s-rundeck` @ `2081783`, `deployconf` main @ `9d5fb1a` (newer than the `ad1c87a` in note 26), `gaia-fe` @ `57ca328`. Branch heads are listed below; cite as `file:line@<branch>-<sha>`.

**Caveat, as in note 26**: the YAMLs are Rundeck SCM exports. The live job definitions live in Rundeck's DB and may have drifted since the last sync commit. Everything below describes **git**, not the live server.

## 1. Branches

`git ls-remote` shows 28 heads. "Job files" means job YAMLs (not READMEs). Dates come from `gh api repos/atypon/rd_jobs/commits?sha=<b>&per_page=1`.

| Branch | Head | Job files | Last commit (UTC) | Author: message | Touches Literatum deploys? |
|---|---|---|---|---|---|
| **common_jobs** (project `Common`) | 9d2caaa | 31 | 2024-01-07 | O. Almomani: s3→prod101 NFS sync job | **Yes**: ConsulPopulate, MountFS, JobWrapper, checkOutGitHub, waitLock, the nightly Consul_Populate_all |
| **gaia-fe_jobs** (project `gaia-fe`) | 14ee144 | 9 | 2024-11-21 | U. Momany: sync | **Yes**: GaiaDeploy, GaiaClusterDeploy, GaiaFeTagRelease, DestroyGaiaCluster |
| **pugrenderer_jobs** (project `Pugrenderer`) | 07f1125 | 3 | 2020-10-17 | U. Momany: LIT-366822 | K8sPugrenderer{Deploy,Destroy,Build} (no product uses it) |
| **statuspage_jobs** | 2d6a05e | 1 | 2024-11-28 | K. Christidis: LIT-538137 | UpdateStatusPage (literatum, manual) |
| **audit_service** (project `Audit`) | 1d06182 | 12 | 2022-01-24 | umomany: syncup? | Audit* DS actions (dead, see §4) |
| cassandra_jobs | 1efcc56 | 5 | 2020-10-02 | S. Shabaneh: last | No DS reference. Casskop helm deploy of k8s Cassandra |
| Literatum | ccbc7f6 | 13 | 2019-07-11 | k8s: repush literatum branch | No DS reference. 2019 "Literatum on k8s" prototype (Build WAR, Deploy Product WAR, bigIp update, Backstage Exec) |
| Services | ec68acf | 22 | 2019-07-11 | k8s: push services | No DS reference. 2019 k8s Solr/ZK/Kafka/Redis/Cassandra/pugrenderer deploy, "ConsulPopulate" 6df45176 (a different job from 3b8f04a7) |
| literatum_amm | 714f4c5 | 22 | 2020-03-03 | fix typo | Amman copy of Literatum. No DS reference |
| services_amm | 57663dc | 26 | 2020-03-03 | fix typo | Amman copy of Services. No DS reference |
| rd_amm | 2958fe7 | 16 | 2020-03-03 | fix typo | Amman copy. No DS reference |
| rundeck_amm (project `Rundeck`) | 01d4d9f | 11 | 2021-11-09 | K8s RD: LIT-432627 | Rundeck self-admin: project Backup (hourly 05-16), Restore, "Generate SCM and ACL" |
| archives | 811a37e | 0 (2 project jars) | 2019-12-30 | update rm | Bootstrap for `Common` and `Rundeck` only (§2) |
| connect | 6d62af1 | 31 | 2025-02-12 | G. Diamantopoulos: remove ArgoCD-managed namespaces | No (Connect/ICS) |
| pkg | 0e259c8 | 102 | 2025-09-03 | K. Christidis: pkg job | No (PKG: Crossref, Pubmed, Elastic, …) |
| _jobs | c56336d | 1 | 2023-03-23 | K. Christidis: PKG-1940 | No (pkghelper) |
| mt_jobs | 275fb99 | 3 | 2025-07-03 | G. Korliaftis: AISERVICES-109 | No (MT, WIRP) |
| docrelease_jobs | 0199486 | 3 | 2023-07-20 | sync | No |
| puppet-master_jobs | 9485cb7 | 1 | 2022-01-18 | LIT-414820 | No (r10k) |
| qaa_jobs | b79cd20 | 1 | 2022-04-23 | initial commit | No (Testypon portal) |
| infographics-extraction_jobs | f2c4ce9 | 1 | 2020-07-16 | init | No |
| scidetect | 5d1f6b2 | 1 | 2019-12-11 | Update job definition | No |
| master | 42bc058 | 0 | 2019-11-13 | cleanup master | stub |
| authorea_jobs, empty_branch, extyles_jobs, k8s-zalenium_jobs, testypon_jobs | fa99fd7 | 0 | 2019-07-02 | Initial commit | empty (README only) |

## 2. How the jobs get into Rundeck

- `k8s-rundeck/kubernetes/rundeck/configuration/postStart.sh:27` clones branch **`archives`**. `:39-51` imports each `*.jar` **only if the project does not exist yet** (`:42`), then runs `rd projects scm perform -i import -a import-all` (`:49`). Only two jars exist: `Common-20191230…` and `Rundeck-20191113…`.
- Their `scm-import.properties` set `scm.import.config.branch=common_jobs` (Common) and `=rundeck_amm` (Rundeck), with `pullAutomatically=true` and `pathTemplate=${job.group}${job.name}-${job.id}.yaml`.
- The other projects (`gaia-fe`, `Pugrenderer`, `Audit`, statuspage) are **not** created by postStart. They come back from project backups via the rundeck_amm jobs "Restore latest backups - from archs/gcp/SCM" (all of them skip projects that already exist). "Generate SCM and ACL" (`rundeck_amm/Projects/Generate SCM and ACL-a6571ee2….yaml:53-69`) sets both git-export and git-import to branch `${project}_jobs`. `audit_service` and `statuspage_jobs` do not follow that naming, so they were configured by hand.
- So the task premise "k8s-rundeck imports them at pod start" is **partly true**: it imports only Common and Rundeck. The rest come from backups. The commit messages on the gaia-fe and audit branches ("sync", "syncup?") are exports **from** Rundeck, so git trails the live server.

## 3. The caller: `RundeckApiService` (opstool `src/com/atypon/opstool/rundeck/RundeckApiService.java`, 167 lines, read fully)

- `:64-67`: an account ending `-cip` goes to `https://rundeck.devops.atypon.com`, anything else to `http://…` (same host, `RundeckUrl.java:5-6`).
- `:76-81`: `-w` with `-p` runs **JobWrapper `3e22a01d-40c8-484d-ad4c-f1d70bbe64cf`** with `-project P -id J -args "<opts>"` (`:108-111`). Otherwise it runs the job id directly.
- `:113-128`: if the start is refused, it prints `ERROR: <body>` and returns null, then prints `Couldn't run the job on Rundeck` (`:91`). **Exit 0.**
- `:131-166`: it streams log entries until `execCompleted && completed`. It retries 503/504 up to 3 times (the counter never resets); any other HTTP error breaks the loop silently. **The execution status is never read.**
- Secret-bearing line at `RundeckApiService.java:73` (API token literal).
- **Consequence**: the DS decides pass/fail only by searching the streamed log for its `validate-txt` substring. Exit codes, Rundeck status and "failed" text are all ignored.

JobWrapper (`common_jobs/macroActions/JobWrapper-3e22a01d….yaml:26-56@common_jobs-9d2caaa`, read fully):
- It parses `-k v` pairs from `args`. For every option of the target job that was **not** passed, it curls that option's `valuesUrl` (invApi → Consul deployconf) and takes the result.
- A failed fetch prints `argument <x> couldn't be fetched from API ...` and sets `api_err=1`, but `api_err` is **never used** (`# ++$api_err`, `:55`).
- It then runs `rd run -i <id> -f -- <all_args>`, so the child's log is streamed inline. That is how child markers reach the DS.
- Consequence: the Rundeck-backed product jobs get cluster, versions, k8s_cluster and so on **from Consul, not from the DS's deployconf file**. A stale Consul means a deploy with stale inputs.
- Secret-bearing lines at `:28` and `:46-48` (job id/token variables).

## 4. DS action → Rundeck job

DS lines are `deployserver/config/actions.xml@b726c83`. Each UUID was confirmed by grepping the full UUID.

| DS action (actions.xml line, marker) | Called how | Job (branch / file @sha) | Steps / nodes / options | Prints marker when… |
|---|---|---|---|---|
| **ConsulPopulate** (`:1157-1163`, `ConsulPopulate execution success`) | direct, `-Environment $populateAccount -clustername $cluster -Purge -Verbose` | common_jobs `Consul/Consul populate from deployconf-3b8f04a7….yaml` @9d2caaa | 1) jobref checkOutGitHub `k8s-consul` master. 2) jobref SvnUpdateNoNFS `-account <env> -Path automation/config/`. 3) script: env→cluster_name `case` (`office-jordan-cip→amm`, `office-santaclara-cip→sc`, `gcp→dr`, **`*→gcp`**), `cd …/k8s-consul/scripts; python3 ConsulPutKV.py -e <env> -c <cluster_name>`. No node filter (runs on the Rundeck server). `keepgoing:false` | `ex_st==0` from the last ConsulPutKV (`:79-85`). The DS `-clustername` is **ignored**: the script derives it from Environment |
| **MountFS** (`:1181-1187`, `MountFS execution success`) | direct, `-HOST "k1 k2" -TARGET dc -ACTION $option -ENVIRONMENT <acct> -VOL $volume` | common_jobs `FileSystem/MountFS-bbe57326….yaml` @9d2caaa | 1-2) checkOutGitHub `k8s-tools` master and `puppet-control` production. 3) script `echo "MountFS execution success"; exit 0`, and the ansible logic after it is all commented out (`:84-99`). ENVIRONMENT is enforced to 9 values, `gcp`/`performance` are not among them. retry 3×30 s | Always, unless a checkout jobref fails first |
| **GaiaDeploy**, non-DC branch (`:1188-1204`, `gaiadeploy execution success` **or `COMPLETED SUCCESS`**) | JobWrapper `-p gaia-fe`: literatum → `8c143b4e`, others → `92c55383` | gaia-fe_jobs `update gaia cluster bundle_version-8c143b4e….yaml` / `…\| LIT-591161-92c55383….yaml` @14ee144 (the two differ only in `cp -r` vs `cp -rf`, `:122-125`) | node filter `.*worker.*`, subset of 1. 1) jobref **ConsulPopulate 3b8f04a7** `-Environment env`. 2) checkOutGitHub `gaia-fe` master. 3) `kubectl get sts … \| grep -w <env>-<cluster>-gaia`, else exit 1 → **errorhandler JobWrapper → `e401d86e` (the *Prod* cluster-deploy job, for both variants)**, `keepgoingOnSuccess:true`. 4) script: Nexus HEAD for default and each version, `confd -onetime` from Consul, `kubectl … create configmap bundles-… \| apply`, sleep 60, then for each pod: wait for the md5 match (≤150 s), then `configinit.sh` | `ex_status==0` (set to 1 only by a `configinit.sh` failure) (`:107-153`) |
| **GaiaClusterDeploy** (`:1350-1360`, `gaia cluster deploy execution success`) | JobWrapper: literatum → `e401d86e`, others → `9c9442ab` | gaia-fe_jobs `Deploy Gaia cluster - Main action - Prod-e401d86e….yaml` / `…Non-Prod-9c9442ab….yaml` (identical apart from name, id and description) | ConsulPopulate jobref, checkOutGitHub gaia-fe, then a script: JVM args, confd, configmap, `helm3 upgrade --install … --wait --timeout 1001s` | `helm3` rc==0 (`:301-305`) |
| **GaiaFeTagRelease** (`:1455-1461`, `gaiadeploy execution success`) | JobWrapper → `d7c3f7c7` | gaia-fe_jobs `Upgrade gaia-fe image version-d7c3f7c7….yaml` | ConsulPopulate, checkout, waitLock lock `gaia_upgrade_<env>_<cluster>`; check sts exists and image tag (else errorhandler → `e401d86e`); waitLock unlock; the same configmap/configinit script as GaiaDeploy, without the `Running` check | `ex_status==0` (`:203-210`) |
| **DestroyGaiaCluster** (`:1644-1650`, `gaiadestroy execution success`) | JobWrapper → `ae64794a` | gaia-fe_jobs `Destroy Gaia Cluster - by clusterName-ae64794a….yaml` | `helm3 delete <env>-<cluster>-gaia`, then deletes PVCs and the configmap (each `\|\| echo "…Not found"`) | helm delete rc==0 |
| **GaiaBuild** (`:1361-1367`, `gaiabuild execution success`) | direct, id `23…` | **Not in any rd_jobs branch** (the only `23…` UUID in the repo is `23298493`, bigIp update, which does not match) | — | Unknown. Hidden/opsOnly (`actions-config.xml:381`) |
| **K8sPugrendererDeploy/Destroy/Build** (`:1368-1388`) | JobWrapper `-p Pugrenderer` → `cbbd4389` / `411a9a73` / `24236c76` | pugrenderer_jobs `Pugrenderer/*` @07f1125 | Deploy: checkout `k8s-pugrenderer`, `helm upgrade --install … --wait --timeout 500`. Destroy: `helm delete --purge` + PVC delete (no `--kubeconfig`). Build: tag check `grep -Fq <ver>` on the registry tag list, else `docker build` + `push` | rc==0 of helm/docker |
| **UpdateStatusPage**, non-"Update Incident" branch (`:237-260`, `COMPLETED SUCCESS`) | direct, `-action create\|delete -product <p>` | statuspage_jobs `Create or Delete a product from Status Page-644be223….yaml` @2d6a05e | node tag `gke-statuspage+rundeck-workers`; `kubectl -n cachet exec … /root/scripts/<action>.sh <product>`; echo `COMPLETED SUCCESS\|FAILURE`; restart statuspage pods. `product` regex `^[a-z]+$` | cachet exec rc==0 (`:65-68`) |
| **AuditDeploy** (`:1651-1657`, `COMPLETED SUCCESS`) | JobWrapper `-p Audit` → `05dfd132` | audit_service `Audit/Deploy Audit - Disabled-05dfd132….yaml` @1d06182 | **`executionEnabled: false`** (`:3`); helm upgrade + rollout status | Prints `execution success`, **never `COMPLETED SUCCESS`** |
| **AuditDestroy / Backup / Restore** (`:1658-1678`, `COMPLETED SUCCESS`) | JobWrapper → `3f042aac` / `007c9c7a` / `779cd9ea` | audit_service `Destroy Audit…`, `Backup Cassandra…`, `Restore Cassandra…` | helm delete + PVC; cassandra backup/restore scripts | Print `auditdestroy/auditbackup/auditrestore execution success`, **never `COMPLETED SUCCESS`** |

Who creates these actions:
- ConsulPopulate + GaiaDeploy: auto after a successful GaiaProductSetAxelVersion with `deployGaia` (`PostExecuteVisitor.java:1009-1051`); GaiaDeploy `waitForId`s ConsulPopulate.
- GaiaDeploy: also added by the product deploy macro (`PreExecuteVisitor.java:2796-2798`, not for readonly/rorehearsal) and `DeployUtils.java:470-484`.
- K8sPugrendererDeploy: `PreExecuteVisitor.java:2807-2808` and `CreateActionMacro.java:959`, only when `isK8sPugrenderer` is set and there is no `pugrendererCluster`.
- **Nothing in DS `src`/`scripts` or `platform-tools` creates MountFS.** It is only a hidden opsOnly action (`actions-config.xml:374`). The doc string "run before/after fc.py" (`:1130`) has no code behind it.

No other repo on the deploy path (platform-tools, opscommon, deployconf, ansible-gaia/pugrenderer/cassandra/inventory, literatum-patch, developer_productivity, gaia, gaia-fe) references any of the 266 rd_jobs UUIDs.

## 5. Verifying the notes/26 claims

| Claim | Verdict | Evidence |
|---|---|---|
| Only ConsulPopulate goes through Rundeck on beta/stag/prod deploys | **Confirmed for the deploy path**, with one caveat | ConsulPopulate is auto-scheduled (`PostExecuteVisitor.java:1020-1039@b726c83`). GaiaDeploy goes to ansible when `isDCGaia()` (`ActionHelper.java:414-429`). deployconf @9d5fb1a: midtierbeta 62 products on `dc-beta` + 1 `aigateway-dc-beta`, staging 73 `dc-stag` + 1, literatum 65 `dc-prod` + 1, and each env's `dc-*` and `aigateway-*` clusters have `k8s_cluster="dc-gaia"` (the single `k1` cluster per env is unused). **But** `isDCGaia()` returns false when the product has no service_cluster or its cluster has no k8s_cluster, and such a product would silently go to Rundeck (not checked product by product). **Caveat**: the Rundeck GaiaDeploy job itself runs ConsulPopulate again as step 1. UpdateStatusPage (literatum only, manual) is also a prod Rundeck action |
| Auto-scheduled after GaiaProductSetAxelVersion | **Confirmed** | `PostExecuteVisitor.java:1009-1051`: only on success and `args.deployGaia`. The cluster arg is `dc`, but the job ignores it |
| MountFS job is a no-op | **Confirmed** | `common_jobs/FileSystem/MountFS-bbe57326….yaml:84@common_jobs-9d2caaa`: `echo "MountFS execution success"\nexit 0` before the commented-out ansible code. It can still **fail** if the `k8s-tools`/`puppet-control` checkout jobrefs fail (`:72-83`), or if Rundeck rejects an ENVIRONMENT outside its enforced list |
| ConsulPopulate with Environment=null reports only the last env | **Confirmed, and it is worse**: the whole loop also uses `-c gcp` | `Consul populate from deployconf-3b8f04a7….yaml:68-85@common_jobs-9d2caaa`: `for env in staging … office-jordan-cip` with `&& ex_st=0 \|\| ex_st=1` overwritten each pass, and `2> $tmpFile` overwritten, so only the last env's stderr is kept. `cluster_name` is computed once from `"null"` → `gcp`, so even office-jordan-cip runs with `-c gcp` instead of `amm`. **Reachability from the DS**: the UI (`ActionArgsVisitorImpl.java:6002`) and the auto path (`PostExecuteVisitor.java:1030`) always set `populateAccount=account`. `null` only happens through REST `/run` with a raw `args` string ending in `null` (`DeployActionSql.java:101-103`, and `ConsulPopulateArgs.serialize` concatenates `null` as `"null"`, `ActionArgs.java:920-922`), or by running the job by hand in Rundeck |
| Rundeck GaiaDeploy reports success with no Running pods | **Confirmed** | `update gaia cluster bundle_version-8c143b4e….yaml:135-153@gaia-fe_jobs-14ee144`: a non-`Running` pod hits `\|\| break` (leaves the wait loop and **skips configinit** for that pod). If no pod matches the label, the `for` loop body never runs. Either way `ex_status` stays 0 → `gaiadeploy execution success`. `performance_sage` short-circuits to success (`:107-109`) |
| RundeckApiService never reads final status | **Confirmed** | `RundeckApiService.java:131-166@opstool-4562351` |
| postStart.sh:27 clones `archives` | **Confirmed** (see §2) | `postStart.sh:27@k8s-rundeck-2081783`. It imports only Common + Rundeck |
| Live jobs may have drifted from git | **Unverified** (no server access) | Last sync commits: gaia-fe 2024-11-21, common 2024-01-07, statuspage 2024-11-28, audit 2022-01-24, pugrenderer 2020-10-17 |

## 6. Failure and false-success patterns (as seen by the DS)

| # | Action | Pattern | Effect in the DS | Evidence |
|---|---|---|---|---|
| F1 | all | Start refused (bad option value, job disabled, auth) → `ERROR: {…}` + `Couldn't run the job on Rundeck`, exit 0 | Failed (missing marker) | `RundeckApiService.java:91,125` |
| F2 | all | Log API error other than 503/504 → silent break | Failed on missing marker, log truncated | `:152-153` |
| F3 | all (JobWrapper) | Option fetch from Consul fails → `argument X couldn't be fetched…`; `api_err` ignored; `rd run` then fails on a required option | Failed (missing marker); the real cause is Consul/invApi | JobWrapper `:49-55` |
| F4 | ConsulPopulate | `ConsulPutKV.py` stderr dumped, then `ConsulPopulate execution failed` | Failed | 3b8f04a7 `:82-85` |
| F5 | GaiaDeploy | `failed to verify default bundle` / `failed to verify bundle V` (Nexus 404), `ERROR: mi… consul token`, confd failure, `Timed out verifying configmap in pods`, `gaiadeploy execution failed` | Failed | 8c143b4e `:112-153` |
| F6 | GaiaDeploy | Cluster sts missing → `Cluster <env>-<cluster>-gaia not found, trying to deploy it` → errorhandler runs the **Prod** cluster-deploy job `e401d86e` even for non-literatum envs (prod-only settings apply only when `env==literatum`, `e401d86e:170-179`) | Continues if that deploy passes | 8c143b4e / 92c55383 `:81-91` |
| F7 | GaiaFeTagRelease | The lock `gaia_upgrade_<env>_<cluster>` is not released if the errorhandler deploy fails (the unlock step is never reached). The next run waits 10 s × 60 and then fails | Failed, repeatedly, until the lock is cleared | d7c3f7c7 `:85-133` |
| S1 | MountFS | Unconditional success echo | **Passes, does nothing** | MountFS `:84` |
| S2 | ConsulPopulate | `Environment=null` loop: last env only, and all envs with `-c gcp` | **Passes while other envs failed** | 3b8f04a7 `:68-85` |
| S3 | ConsulPopulate | Every env outside the case list (staging, literatum, midtierbeta, …) gets `-c gcp`. What `-c` does is in `k8s-consul/ConsulPutKV.py` (not cloned). The scheduled "ConsulPopulate GCP" variant maps `*→dc` instead (`d0321e8b:77-79`) | **Unverified** whether the wrong target is written | — |
| S4 | GaiaDeploy | No pod `Running`, or none match the label → success. `performance_sage` → success | **Passes, config not applied** | 8c143b4e `:107-153` |
| S5 | GaiaDeploy | Nexus check fails only on HTTP **404**. 000/401/5xx (Nexus down, auth) pass the check | Passes the check; `configinit.sh` inside the pod does its own check (`gaia-fe/kubernetes/gaia/configinit.sh:8,14`) | 8c143b4e `:112-118` |
| S6 | GaiaDeploy | `kubectl create configmap … \| kubectl apply` is unchecked. If apply fails and pods are not Running → success. If pods are Running → md5 timeout → fail | Mixed | 8c143b4e `:129-131` |
| S7 | GaiaDeploy (DS) | `or-validate-txt "COMPLETED SUCCESS"` (`actions.xml:1203`). No rd_jobs file prints that text, so it only matters on the ansible branch. It is harmless for Rundeck today | — | grep for `COMPLETED SUCCESS` across all branches: only statuspage `644be223:67-68` |
| S8 | K8sPugrendererBuild | `grep -Fq <ver>` substring match on the tag list: version `1.2` "exists" if `1.2.3` does, so the build is skipped and reported as success | Passes with the wrong image | 24236c76 `:41-42` |
| S9 | UpdateStatusPage | Prints `COMPLETED SUCCESS` from the cachet exec rc; the pod restart after it is unchecked | Correct for the create/delete itself | 644be223 `:65-71` |
| D1 | AuditDeploy/Destroy/Backup/Restore | The jobs print `…execution success`, but the DS wants `COMPLETED SUCCESS`. AuditDeploy's job is also `executionEnabled:false`. AuditDestroy's `[[ "$X"=="true" ]]` has no spaces, so it is always true (`3f042aac:47`) | **Always Failed** (dead actions) | §4 |
| D2 | GaiaBuild | Job `23…` not in git | Unknown | §4 |

Mitigation that already exists: **`Consul_Populate_all`** (`common_jobs/Consul/Consul_Populate_all-fbac1781….yaml@9d2caaa`) is **scheduled daily 00:00**. It runs 3b8f04a7 once per env (11 envs) and does aggregate failures (`failures="$failures $i"` → exit 1). **"ConsulPopulate GCP" d0321e8b** runs daily at 01:00. So a stale Consul after a silent DS-side failure lasts at most about a day, if those schedules are live (**Unverified**). Nobody watches these scheduled failures from the DS.

## 7. The other projects, in short

- **gaia-fe_jobs**: see §4. Also: `Destroy Gaia` (4a96f04f), `Destroy Gaia Cluster` (faa78d4e) and `update … - noProds` (375a9b45, errorhandler → e401d86e) are not called by the DS. All gaia jobs run ConsulPopulate first, check out `gaia-fe` **master** (not a release tag), and read everything from Consul through `valuesUrl`.
- **cassandra_jobs** (2020): Casskop operator + helm (`DeployCassandraFromEnv` 78550678). `helm3 install casskop … || true` and `kubectl apply crd … || true` hide failures, and the final `$cmd` rc decides the result. It has no markers the DS looks for and no DS caller. On the Literatum path, Cassandra is ansible-cassandra.
- **pugrenderer_jobs** (2020): k8s pugrenderer (§4). Not used: no product has `<k8spugrenderer>`, and `requiresK8sPugrenderer` auto-cancels.
- **Literatum / literatum_amm / rd_amm** (2019-20): a k8s Literatum prototype (Build Literatum WAR, Deploy Product WAR, bigIp update, Scale Deployments, Backstage Exec, ops-tools build). **Nothing references them.** The only "success" text is `echo "successful .."` in `run ansible build` (10d5d58d).
- **Services / services_amm** (2019-20): k8s Solr/ZK/Kafka/Redis/Cassandra/PR/consumer images and deploys, plus LB-F5 refresh. Not referenced. `Services/ConsulPopulate-6df45176` = common_jobs "Consul Modify and Populate -- Review" (same UUID). It is not the job the DS calls.

## 8. Coverage

**Read fully (safe_view):**
- common_jobs: ConsulPopulate 3b8f04a7, MountFS bbe57326, JobWrapper 3e22a01d, checkOutGitHub 42d43b44, Consul_Populate_all fbac1781, ConsulPopulate GCP d0321e8b (lines 20-91).
- gaia-fe_jobs: 8c143b4e, e401d86e (option `valuesUrl` lines skipped), d7c3f7c7 (lines 1-12 and 60-214), ae64794a. 92c55383 and 9c9442ab were compared by `diff` against their twins.
- pugrenderer_jobs: all 3 (Destroy from line 25, Build from line 30).
- statuspage_jobs: 644be223.
- audit_service: 05dfd132 fully, 3f042aac lines 20-61.
- DS: `actions.xml` 222-260, 1145-1215, 1345-1392, 1452-1462, 1640-1680; `PostExecuteVisitor.java` 995-1060; `DeployActionSql.java` 40-140; `ActionArgs.java` 905-935; `ActionHelper.java` 414-430; `PreExecuteVisitor.java` 2785-2812.
- opstool `RundeckApiService.java`, `k8s-rundeck` `postStart.sh`, `gaia-fe/kubernetes/gaia/configinit.sh`.
- Archive jar `scm-import.properties` (grep of branch/url/pattern keys).

**Sampled (grep only):**
- Marker and `exit` grep over audit_service and pugrenderer.
- Names and markers for Literatum, Services and cassandra_jobs, plus `DeployCassandraFromEnv` lines 1-8 and 60-142.
- rundeck_amm Projects/* (grep).
- Schedule scan of all branches.
- The "any rd_jobs UUID" grep over the deploy-path repos.
- deployconf gaia `service_cluster` / `k8s_cluster` counts.

**Not read:**
- connect, pkg, mt_jobs, docrelease_jobs, qaa, puppet-master, infographics, scidetect, _jobs (they don't touch Literatum).
- The audit Backup/Restore bodies (beyond the marker grep), `SvnUpdateNoNFS`, `waitLock`.
- `k8s-consul/ConsulPutKV.py` (repo not cloned).
- The live Rundeck server.

## Secret-bearing lines (values not recorded)

- `opstool/…/RundeckApiService.java:73`
- JobWrapper `:28`, `:46-48`
- 3b8f04a7 `:57`, `:71`, `:74`
- d0321e8b `:79`, `:82`
- 8c143b4e / 92c55383 `:112`, `:115`, `:119-121`
- d7c3f7c7 `:149`, `:154`, `:160-161`
- e401d86e `:143`
- checkOutGitHub `:104-106`, `:123`, `:129`, `:139`
- rundeck_amm `Generate SCM and ACL…:95` (LDAP username/password literal: **committed credential, should be rotated**)
- rundeck_amm Backup `:25-31`
- `k8s-rundeck/…/postStart.sh:13,16-20,24,26-27,33`
- `k8s-rundeck/run command with token for admin` (not opened)
- `gaia-fe/kubernetes/gaia/configinit.sh:13,19`

Extracted archive-jar contents are in the session scratchpad only.
