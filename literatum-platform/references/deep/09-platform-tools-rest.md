# 09 — platform-tools: every other script the Deploy Server calls

**Scope.** This note covers every platform-tools script that a Deploy Server (DS) action calls and that note 02 does not cover. Note 02 already covers rebuild/patch/redeploy/restart, setprod, sync_branches, run_gradle/run.sh, the styleguide chain and `platform-tools/deployserver/*`.

**Repos.**
- `platform-tools` master `b00c49f`.
- `deployserver` master `b726c83` (2026-09-24).
- Read-only throughout.

**Method.**
1. Parsed every `<action>` in `deployserver/config/actions.xml`: 307 actions, of which about 150 reference a `.sh`/`.py`, `run tool`, `run_gradle` or `rstrt`.
2. Grepped `deployserver/src/**/*.java` for script invocations.
3. Resolved each script against `git ls-files` of platform-tools.

**Citation convention.**
- `file:line` is relative to `platform-tools/`.
- `DS:` = `deployserver/src/com/atypon/deployserver/server/`.
- `actions.xml:` = `deployserver/config/actions.xml`.

**Who read what.**
- Me: the deploy-adjacent set (§2.1).
- Two forks of me with the same rules read the DB/reprocess set (§2.2) and the ops/tooling set (§2.3). I use their findings with their citations.

**Secrets.** No secret value is reproduced here. Secret-bearing lines are listed by location in §5, for rotation.

---

## 0. DS verdict mechanics that matter for these actions (new vs 02)

- **actions.xml validators** (DS:`actions/ActionSpec.java:19-49`, `actions/IValidateResponse.java`):
  - Validators are combined in document order. `validate-txt` = AND contains(X). `or-validate-txt` = OR contains(X). `invalid-txt` = AND NOT contains(X).
  - "Contains" means *any line of the whole action log* (DS:`actions/ValidateResponseTxt.java:19-31`).
  - **An action with no validator is always Success** (`IValidateResponse.Yes`, ActionSpec.java:46-48).
  - `validate-txt value=""` (DbAdminsList, actions.xml:546) matches any non-empty log.
- **The typed command text is in the log too.** `JschConnection.java:133` writes `DrainResponse … (ssh) <cmd>` after every command, and the pty echoes the input. I checked every action for a validator string that literally appears in its own command text. Only `CleanupLocalOrphanDbs` does ("Cleanup Database on Dev DB completed successfully"). That action can therefore **never fail**.
- **Visitor actions** (no actions.xml entry) use `SshExecutedVisitor`, whose default status is **`Cancelled`** (DS:`visitor/SshExecutedVisitor.java:42`). An action type without a parser method, such as UpdateYaegerVersion, therefore always ends Cancelled (DS:`DeployDaemonHelper.java:523-531`).
- **Exit codes are never read**, except where the DS line itself chains `[[ $? == 0 ]] &&` (DbAdminsList) or calls the `AnsibleCheckExitCode` library. That library echoes `COMPLETED SUCCESS|FAILURE` from `$?` of the *previous typed line* (actions.xml:2794-2798).
- **`(echo … && exit 1)` is a subshell exit.** Many scripts below use `[[ $? -eq 0 ]] && echo ok || (echo fail && exit 1)`. The subshell exits and the script carries on. I call this the "subshell-exit" pattern.

---

## 1. Action type → script table

Legend for "Cov":
- **09** = read fully in this note.
- **02** = covered in note 02.
- **ext** = the script lives outside platform-tools (repo or path named); not read.
- **MISSING** = not in any repo we have.

| DS action | Command (abridged) | DS pass/fail text | Script | Cov |
|---|---|---|---|---|
| CipDomainFixup | litconfig refresh; setprod; `run_gradle.sh main -Dmain.class=…CreateCipDomain` | `BUILD SUCCESSFUL` | run_gradle.sh | 02 |
| FullGC / KillJDBCConnections | `reinitializeConnPool.sh -p -f -t gc\|closeConn` | **none (always Success)** | reinitializeConnPool.sh, prodPID.sh | 09 |
| CipProductCreateFS | setprod; `run tool create.publisher.cip`; `rsyncContent.sh -e cip -a -p -f` | `Copied Successfully` | rsyncContent.sh | 09 |
| CipProductRemoveDbAndFs | `~/scripts/cipRemoveDbAndFs.sh -p -f` | `Removing FS` | cipRemoveDbAndFs.sh | 09 |
| CipRemoveFileSystem / CipRemoveDeployedDirectory / RemoveDeployedDirectory / CipRemoveBackstageLogs | `~/scripts/CipRemove*.sh -p -f` | `Removed successfully` OR `nothing to delete` | CipRemove*.sh | 09 |
| CipRemoveDatabase | `~/scripts/CipRemoveDatabase.sh -p -f` | `Db removed successfully` | CipRemoveDatabase.sh (sources developer_productivity/schemeConfig.sh) | 09 |
| ReportUserPermission | setprod; `list_users_permission.sh T` | `BUILD SUCCESSFUL` | list_users_permission.sh | 09 |
| AutoRestartEnable/Disable, LiteratumQuarantineEnable/Disable | `autoRestartToggleSwitch.sh -p -a -t [-s QUARANTINE]` | `task finished successfully`, not `…unsuccessfully` | autoRestartToggleSwitch.sh (edits jDumps.sh) | 09 |
| CfInvalidateCache | `InvalidateCloudflareCache.py -p -f` | `Finished Invalidating Cloudflare Cache` | InvalidateCloudflareCache.py | 09 |
| Product/MultiTenant/Db/DockerAlertsSilence | `alertManagerSilencer.py <type> …` | `Alert silencer finished successfully` | alertManagerSilencer.py | 09 |
| HttpsSwitcher | `httpsSwitcher.sh P T type debug commit` | **none** | httpsSwitcher.sh | 09 |
| GrantIndividualPermission | `appendToPermissionFile.sh …` | `Successfully injected permission file` | appendToPermissionFile.sh | 09 |
| WorkFlowSetter / SolrIndexSync / GenerateSmartExpansions | setprod; `backstage.sh <target> …` | `has been updated to new value` / `BUILD SUCCESSFUL` | backstage.sh (+vpenv.sh) | 09 |
| DtsGetter / DtsSetter | `dtsGetter.sh -p -f -t -d` / `dtsSetter.sh -p -f -t` | `disabling the DTS for` / `BUILD SUCCESSFUL` | dts*.sh | 09 |
| SetPatchRelease / MajorUpdateLiteratumProps / CreatePatchPlan | `major_upgrade_post_actions.sh -b REL -a …` | `COMPLETED SUCCESS` | major_upgrade_post_actions.sh, setup_literatum.sh | 09 |
| VIndex | `v-index.sh …` | `Ran successfully` | v-index.sh | 09 |
| ReloadSamlData / InstallSamlData | `updateSamlData.sh -f` / `installSamlData.sh …` | `Done successfully` | *SamlData.sh | 09 |
| HBSDetector | `hbs_detector.sh -p -f -t -i` | `EXECUTION SUCCESS` OR `File is empty or contains Headers row only` | hbs_detector.sh | 09 |
| ReportEscapedRevisions | setprod; `escaped_revisions_cron.sh` | `ReportEscapedRevisions done successfully` | escaped_revisions_cron.sh | 09 |
| DeployConfValidation | `deployConfValidation.sh -a -r` | `Validation has been completed` | deployConfValidation.sh | 09 |
| CheckWebsiteAdminConfig / CheckConfGets | `checkWebSiteAdminConfig.sh …` | `BUILD SUCCESSFUL` | checkWebSiteAdminConfig.sh | 09 |
| HostWarmupTest / HostEssentialTest / HostTest (visitor) | `host_test.py -p -f -m -t -i -a` | first of `***Test Is Succeeded***` / `***Test Is Failed***` (from the test container) | host_test.py | 09 |
| DbClone / DbCloneBackup/Copy/Restore/Remove (visitor) | `cd ~/scripts; do_clone.sh …` | `Backup was done successfully` + `Restore was done successfully`, etc. | do_clone.sh | 09 (fork A) |
| DbOptimize (visitor) | `do_optimize.sh -t -n -p` | `DB optimization completed successfully` | do_optimize.sh | 09 (A) |
| DbFlexClone / DbReportFlexClone / DbArchiveFlexClone | [`do_kill.sh … softDrop`]; `do_dbflexclone.sh …` | `Congratulations!` (printed by a Windows ps1, not in repo) | do_kill.sh, do_dbflexclone.sh | 09 (A) |
| PB2backup / PB2restore / PB2restoreLast | `BackupPB.sh` / `RestorePB.sh` | `Backup/Restore has been successfully done` | BackupPB.sh, RestorePB.sh | 09 (A) |
| BuildDockerDatabaseImage* / UpdateDockerDatabaseFromBackup | `cd ~/scripts/docker; ./build_docker_db_wrapper.sh …` | `DONE SUCCESSFULLY` | build_docker_db_wrapper.sh (→ ext ansible-actions.py) | 09 (A) |
| SubmitReprocess / CheckReprocess / DigitalObjectReprocess (visitor) | `cd ~/scripts/reprocess; ./submit_reprocess.sh` / `check_reprocess.sh` / `digital_object_reprocess.sh` | see §2.2 | reprocess/*.sh | 09 (A) |
| Submit/CheckPassportReprocess, PassportDigitalObjectReprocess (visitor) | `./passport_content_reprocess.sh -s submit\|check` | `BUILD SUCCESSFUL` / `No dois to reprocess.. Exiting` vs `BUILD FAILED` | passport_content_reprocess.sh | 09 (A) |
| AddNonWebInstance (visitor) / FinalizeReprocess | `./add_remove_Non_web_instance.py -a add\|remove -c` | `The rbackstage server [h]`, fail on `error`/`ERROR` / `Removing the rbackstage done successfully` | add_remove_Non_web_instance.py | 09 (A) |
| CustomReprocessProduct | `./reprocess_LIT-516738.py` | `CustomReprocess done successfully` | processing_scripts/reprocess_LIT-516738.py | 09 (A) |
| AlertExternalEnable/Disable | `cd /atypon/scratch/personal/shared/; ./pingdomApi.sh …; catchpointApi.py …` | `unpausing` / `pausing` | **shared-dir copy** of pingdomApi.sh (repo copy read) + catchpointApi.py | 09 (B) |
| AlertInternalEnable/Disable | `cd /atypon/scratch/personal/shared/; EmailAlertStarter.sh …` | `unpausing` / `pausing` | EmailAlertStarter.sh | **MISSING** (shared dir only) |
| UpdateStatusPage | ansible-actions status-page, or pingdomApi.sh + opstool Rundeck | `COMPLETED SUCCESS` | pingdomApi.sh | 09 (B) |
| PagerDutyShifts | `cd ~/scripts; python3 pd_shift.py …` | `Successfully created` | pd_shift.py | 09 (B) |
| MissingMerges | `python3 MissingMergeDetector.py …` (no cd) | `Done successfully` | MissingMergeDetector.py | 09 (B) |
| VideoCodec / CloudflareVideoAnalytics / CloudflareVideosData / CfVideosCleanup | `video_codec.sh` / `video_analytics_v1.py` / `stream_analytics_v2.py` / `deployserver_stream_bulk_delete.py` | `Task finished successfully` / `Result generated under` / `Videos cleanup Completed` | same | 09 (B) |
| CloudFlareRecordAdd/Remove | `cloudflare-dns.sh -a add\|delete -n P-F` | `DNS record added/deleted successfully` | cloudflare-dns.sh | 09 (B) |
| EnableArgoTunnel | `enable_argo_tunnel.sh …` | **none** | enable_argo_tunnel*.sh | 09 (B) |
| SyncGitWithSvn | `svn_to_git_setup.sh ~/source` | **none** | svn_to_git_setup.sh, svn_to_git_sync.sh | 09 (B) |
| GitBranchCreate (cms) / CreateCmsJenkinsPipelineFromTemplate / CreateCmsReleaseByJenkins | `cms/handle_cms_cut_branch.sh` / `cms/handle_cms_jenkins.sh` | `Done successfully` | cms/*.sh | 09 (B) |
| GitBranchCreate (other) / GitMerge / GitMergeRev / GitBranchRemove / DryMerge / CollectMissingTickets / CheckoutMajorBranchByJenkins / TriggerRootPomReleaseJenkinsJob / AddToPermissionGroup / RevokeDsPermissions / PrepareVM / DestroyVm / RestartDevVm / ConfigureCfZt / ConfigureEphemeralLitRoute | `~/sourcegit/deployserver/scripts/*.sh` | various | deployserver repo `scripts/` | **ext** (deployserver repo; `gitMerge.sh` also in platform-tools/deployserver, 02) |
| AtmTraining | `AutomateATM.sh -p -b -j -c -n` | `ATM has been finished successfully` | AutomateATM.sh | 09 (B) |
| RunImageOptimizerTool | `image_optimizer.sh P` | `Finished at` | image_optimizer.sh (→ ext image-optimizer repo) | 09 (B) |
| GatherProductWidgets / AnalyzeWidgets | `generate_widget_report.sh` / `analyze_widgets_report.py` | `Product csv file created` / `Excel Sheet Created` | same | 09 (B) |
| UpdateCounterRobotsList | `insightsops/UpdateCounterRobotList.sh` | `…committed to git OR there is nothing to commit` | same | 09 (B) |
| AddGitbotFeature | `gitbot/addGitbotFeature.py …` | **none** | same | 09 (B) |
| FirewallsReport / UpdateAtyponLifecycle / ToolOpstoolInstall / SyncWebdavSaml | puppet_workstation_report.sh / updateMjrBranchesList.sh / build_opstool.sh / `/na101/home/literatum/scripts/webdav_dr_saml_sync.sh` | `Report generated` / `Updated MJR_BRANCHES_LIST` / `Finished Successfully` / `All syncs completed at ` | same | 09 (B) |
| AnalyticsSyncEvents / IamRedisCacheLoader | ansible-playbook analytics_events/* / `operations/cron/pericles_culp_resync.sh` | **none** | same | 09 (B) |
| PyroscopeProfile | `pyroscopeProfile.sh P MIN` | `PROFILING_TRIGGERED`, not `ERROR:` | same | 09 (B) |
| UpdateYaegerVersion (visitor) | `cd ~/scripts; ./updateYaegerOnLiteratumBranches.sh -v -t -b` | **no parser → Cancelled** | same | 09 (B) |
| (TestUtils helper) | `cd ~/scripts/xmlqaauto; ./pull_deploy_xmlqaauto_jar.sh V` | — | same | 09 (B) |
| CreateNewEmployee / DeleteEmployee / EnableRevisionDeletion / DisableRevisionDeletion / SiteConfigBackup / SiteConfigRestore / CreateArgoTunnelSecondaryDomain / RunJavaCodeOnAll / ToolMarlinSingleCert / ValidateWebOnROMode / GatherFactsForJenkinsJob | `run tool <target>` or `run_gradle.sh <task>` (Ant/Gradle targets in `operations/tools/tool.xml`, not scripts) | `BUILD SUCCESSFUL` / target-specific text | run.sh / run_gradle.sh (02); targets not read | 02 / targets not read |
| RunCLI / CheckStyleguideMaintBranches | `deployserver/run-cli.sh` / `gitBranchCheck.sh` | `BUILD SUCCESSFUL` / none | same | 02 |
| StyleguideTemplateUpdate / SqlPatchCheck / GenerateStyleguidePackage | `styleguide/styleGuideUpdate.sh` / `deployserver/checkSqlPatchStatement.sh` / `packageStyleguide.py` | — | — | **MISSING** (also in 02 §1.2) |
| ActivateNonprodPipelines / K8sJavaEtlCleanup / InsightsAlertsCheck / InsightsGCRCleanup / UserInterests(Init) / Insights* | bare `ActivateNonprodPipelines.sh`, `. cleanup-javaetl.sh`, `alerts_k8s.sh`, `. gcr-cleanup.sh`, `./user-interests*.sh`, ssh to 3.87.14.135 | mostly `invalid-txt` only | insights tooling | **MISSING** (insights host/PATH, not platform-tools) |
| DbProductRestore / LocalDbCloneAndRestore / LocalAndCipT1DbRemove / DbProductBackup / DbReportProductBackup / Cip*Restore* / Cassandra*Backup/Restore / Db*CleanupLocalBackupOnFTP / CipLocalDB*Remove* / CipCleanupLocalDbBackup | `~/sourcegit/developer_productivity/*.sh` | `…finished successfully` etc. | developer_productivity repo | **ext (not cloned; unlisted repo, see §4)** |
| GCP* / LBPoolConfig / ListProductClones / ProductFlexClone / RunPuppet / DbAdminsList / LiteratumPropsChange / Create/DeleteInfraNewEmployee / ElkFilebeatDeploy / SftpUsers | terraform-infra/deploy_dr.sh, /root/lb, /root/ansible-fc/fc.py, puppetagent.sh, infra-scripts/sql-audit, PropsManagement, /home/infrauto/bin, ansible elk, /archive/s/ansible-sftpusers | various | — | **ext** |

---

## 2. Per-script sections

### 2.1 Deploy-adjacent set (read by me)

### reinitializeConnPool.sh (90 lines, R)
- **DS actions:** FullGC → `reinitializeConnPool.sh -p P -f F -t gc`; KillJDBCConnections → `… -t closeConn` (actions.xml:122-131). **No validator on either**, so both are always Success (`IValidateResponse.Yes`, DS:`actions/ActionSpec.java:46-48`).
- **Steps:** sources `functions.sh` and `bashLogging.sh` (:2-3). `lll P | jq .servers` must contain `$HOSTNAME`, else `exitHandler … 2` (:53-54). deployconf `product/@enabled` must be `true`, else exit 6 (:65-66). `pid=$(prodPID.sh P[:F] true)` (:69). Then, per `-t`: `lock.py`, `kill -12 $pid` (closeConn), `jcmd $pid GC.run` (gc), `unlock.py` (:84-87). With no `-t`: lock, sleep 60, GC, signal 12, unlock (:72-82).
- **prodPID.sh (44 lines, R):** only knows Resin. It reads the web port from `$DEPLOY_HOME/conf/resindeploy.main.conf`, then `sudo netstat`, then `resinctl status`/`resin.sh status` (prodPID.sh:28-40). With no Resin conf (every Tomcat deploy, i.e. ≥2210) it prints `can't find pid` and exits 1 (:41).
- **Silent failure:**
  - `[[ $? -ne 0 ]]` at :71 tests the exit code of `logInfo` on :70, not of `prodPID.sh`. The check never fires.
  - On Tomcat hosts `pid` is the string `can't find pid`. `kill -12 can't find pid` and `jcmd can't …` fail, their errors are not checked, and the action is still Success.
  - **Net:** on current Tomcat products FullGC and KillJDBCConnections do nothing and report Success.
- **Hosts:** the local web host only. `lll` is a functions.sh/alias lookup (inventory).

### rsyncContent.sh (273 lines, R): CipProductCreateFS
- **DS:** `cd ~/.litconfig; git reset --hard; git clean -fdx; git pull origin main; setprod P F; run tool create.publisher.cip; rsyncContent.sh -e cip -a ACCT -p P -f P-F`. Validator: `Copied Successfully` (actions.xml:132-141).
- **Steps (cip, no `-t`):**
  - The server defaults to `tools-1` (:221-223).
  - It lists the products that have `cms/` and `dos/` under `cip@tools-1:/na102/home/staging/publisher/*` into `/tmp/cmsProducts.txt` and `/tmp/dosProducts.txt` (:229-230).
  - `syncCipCms` rsyncs `…/<P>/cms/core` into `~/publisher/<P-F>/cms`, and `syncCipDos` rsyncs `…/<P>/dos` into `~/publisher/<P-F>/` (`--ignore-existing`, output through `|& tee /tmp/rsyncContent<P>.txt`) (:139, :155).
  - Each sync prints `Copied Successfully` only if the tee file is non-empty, has no `error` (case-insensitive) and contains `total size is` (:140-144, :156-160).
- **False success:**
  - The DS passes no `-t`, so both CMS and DOS run. **Either** one printing `Copied Successfully` satisfies the DS, even when the other printed `There is an Error`.
  - `run tool create.publisher.cip` (the Ant target that creates the publisher FS) is not validated at all.
  - `grep -qi "${Product}"` against the product list is a substring match (:137, :153): product `acm` matches `acmx`.
  - `/tmp/cmsProducts.txt`, `/tmp/dosProducts.txt` and `/tmp/rsyncContent<P>.txt` are fixed names shared between concurrent runs on one host.
- **Hosts:** `cip@tools-1` (staging publisher mirror on /na102); target is `~/publisher` on the CIP host.

### cipRemoveDbAndFs.sh (96 lines, R): CipProductRemoveDbAndFs
- **DS:** `~/scripts/cipRemoveDbAndFs.sh -p P -f F`. Validator: `Removing FS` (actions.xml:142-147).
- **Steps:**
  - Reads the DB name and server from `~/deployconf.xml` via xmllint (:66-67).
  - `sqsh` sets the DB to SINGLE_USER, then drops it (:79-80). Those two lines are secret-bearing: DB credentials are hard-coded on the command line.
  - Then `cd ~/publisher; rm -rf P-F` (:86-87) and `cd /local/home/$USER/servers; rm -rf F` (:92-93).
- **False success (the worst in this set):**
  - The validator string `Removing FS` is printed **unconditionally at :84**, before the FS step, whatever happened to the DB drop.
  - The failure branches `|| (echo … && exit 1)` run `exit` in a subshell (:82, :89, :95), so the script never stops.
  - `$?` at :82 is the drop's status only; the SINGLE_USER step is unchecked.
  - Both `cd` calls are unchecked. If `/local/home/$USER/servers` is missing, `rm -rf $Family` runs in `~/publisher` (:92-93).
  - **Net:** the action is Success even when the DB was not dropped.

### CipRemoveFileSystem.sh (61, R), CipRemoveDeployedDirectory.sh (67, R), CipRemoveBackstageLogs.sh (60, R), CipRemoveDatabase.sh (69, R)
- **DS** (all `-p P -f F`, actions.xml:148-174; `RemoveDeployedDirectory` 1563-1569 reuses CipRemoveDeployedDirectory.sh on any account):
  - The first three are validated by `Removed successfully` or `nothing to delete`.
  - CipRemoveDatabase is validated by `Db removed successfully`.
- **What each removes:**
  - FS: `~/publisher/P-F` (CipRemoveFileSystem.sh:54-56).
  - Deploy dir: `/local/home/$USER/servers/F` plus `~/warfiles/…` (CipRemoveDeployedDirectory.sh:53-64).
  - Backstage logs: `$HOME/logs/backstage/$HOSTNAME/F` (CipRemoveBackstageLogs.sh:53-55).
  - DB: drop via a secret-bearing sqsh line (CipRemoveDatabase.sh:64-67). It sources `~/sourcegit/developer_productivity/schemeConfig.sh` (:2), **another repo**.
- **Silent paths:**
  - "Not found" prints `…nothing to delete\n` and exits 0. That counts as Success even when the reason is an unchecked `cd` that failed, because the directory test then runs in the wrong cwd (:54-58 in each of the three).
  - CipRemoveDeployedDirectory prints `Removed successfully..` **unconditionally at :68**. Its failure branches are subshell exits (:61, :66).
  - **Bug at CipRemoveDeployedDirectory.sh:64:** `rm -f ~/warfiles/$ProductName_$Family.*` expands the undefined variable `$ProductName_`, so it becomes `~/warfiles/F.*`. It never matches the real `P_F_<date>.war` names (02 §3.4), so **old WARs survive** "RemoveDeployedDirectory". A later HostDeploy on a re-created family picks the lexicographically latest old WAR (02 §5.1).
  - CipRemoveDatabase is the one done right. It treats any sqsh output as failure and exits 1 (:65, :67), and prints success only at the end (:68).

### list_users_permission.sh (77, R): ReportUserPermission
- **DS:** `setprod P F; ~/scripts/list_users_permission.sh <ticket>`. Validator: `BUILD SUCCESSFUL` (actions.xml:280-286).
- **Steps:**
  - Copies `~/scripts/ListUsersPermission.java` into `/tmp/<P>_list_users_permission_<T>` (:36-56).
  - `setprod P`, then `run tool script -Dscript=… -Dargs="<csv> <T>" -Djvm.args=-Xmx16G` writes `/archive/literatum/list_users_permission/<T>/<P>.csv` (:69-70).
- **Notes:**
  - A missing ticket only prints `ERROR: No jira ticket provided` and continues (:20-22).
  - The verdict is Ant's `BUILD SUCCESSFUL`. `run` returns run.sh's code, whose env guards `exit` 0 (02 §2.7).

### autoRestartToggleSwitch.sh (91, R): AutoRestartEnable/Disable, LiteratumQuarantineEnable/Disable
- **DS:** `autoRestartToggleSwitch.sh -p P -a ENABLE|DISABLE -t T [-s QUARANTINE]` (actions.xml:362-402). Validator: `task finished successfully` **and not** `task finished unsuccessfully`.
- **What it changes:** the literatum watchdog lists in `~/scripts/jDumps.sh`: `skipRestartProds="x(DUMMY|…)"` at jDumps.sh:137, and `skipLiteratumQuarantineProds="x(QRNTN|END)x"` at :150. DISABLE inserts `P|` after the marker, ENABLE removes it (:62-84).
- **Steps:**
  - It must run as `USER=literatum` (:42), and `list.py` must know P (:43).
  - `cd ~/scripts; git reset --hard origin/master; git pull; sed -i …; git commit …; git push` (:68-73, 78-83). The commit is on the **platform-tools master branch, pushed from the host**.
- **Failure modes:**
  - Any git step failing sets `fail_ex_code=1`, which prints `task finished unsuccessfully` (:88). The script handles this correctly.
  - "Already enabled/disabled" calls `usage … 0` (:66, :76). That exits 0 **without** the success string, so the **DS shows Failure for a no-op**.
- **Side effect for triage:** `git reset --hard origin/master` in `~/scripts` on the literatum tools host discards any hot-patched local script. If a script "suddenly changed behaviour" on literatum, check whether an AutoRestart/Quarantine toggle ran.

### InvalidateCloudflareCache.py (132, R): CfInvalidateCache
- **DS:** `InvalidateCloudflareCache.py -p P -f F`. Validator: `Finished Invalidating Cloudflare Cache` (actions.xml:410-415).
- **What actually runs:** the first `__main__` block (:23-26) builds a stub class that only prints the two arguments. It then prints `>>> Finished Invalidating Cloudflare Cache` and calls `sys.exit(0)`. Everything below :29 is dead code, and its purge request is itself commented out (:121-122).
- **Net: the action always succeeds and purges nothing.**
- A secret-bearing comment sits at :124, and the dead code has hard-coded auth headers (:70-73, 90-93, 118).

### alertManagerSilencer.py (309, R): Product/MultiTenant/Db/DockerAlertsSilence
- **DS:**
  - `alertManagerSilencer.py $alertType -p P --silencefor N` (actions.xml:416-443)
  - `… -c CLUSTER …`
  - `… jdbc $dbServer …` / `… $alertType $dbName …`
  - `docker --host S …`
  - Validator: `Alert silencer finished successfully`.
- **Steps:**
  - argparse subcommands per alert type (:33-259).
  - The matchers are **every non-empty argparse dest** (`alert_type`, `product`, `envtype`, `sub_alert_type`, …) as literal equality matchers (:270-274).
  - It POSTs to `https://alertmanager.devops.atypon.com/api/v1/silences`, falls back to http (:288-302), fails on non-200 (:304-307), and prints the success string (:310).
- **False success:** a 200 only means Alertmanager stored the silence. If the argparse dest names differ from the real alert label names, **the silence matches nothing**, yet the DS shows Success. Not verifiable here: needs the Prometheus rule labels (`deployserver/config/prom-rules` could confirm).
- **Failures:**
  - If both requests throw, `response` is unbound, so a NameError traceback leads to Failure (:301-304).
  - `/api/v1` was removed in newer Alertmanager versions. A 404 or 410 makes it fail loudly.
  - DbAlertsSilence passes `$dbServer`/`$dbName` **positionally**, but the `jdbc` and `db_connections` parsers only accept `--dbserver`/`-d`. Unless the DS value already contains the flag, argparse exits 2 with a usage error, so the action fails.

### httpsSwitcher.sh (43, R): HttpsSwitcher
- **DS:** `~/scripts/httpsSwitcher.sh P T type debug commit`. **No validator, so always Success** (actions.xml:700-705).
- The core command lines (:30-31) are secret-bearing (DB access).
- A non-zero exit only adds a Jira comment and `break`s (:32-33). All Jira calls go to `/dev/null`.

### appendToPermissionFile.sh (28, R): GrantIndividualPermission
- **DS:** validated by `Successfully injected permission file` (actions.xml:706-711).
- **Steps:** runs in `~/sourcegit/deployserver/config`: `git reset --hard; git pull` (unchecked), appends CSV lines to `permission.csv`, `git commit … && git push`, then `echo $(yes | cp … ~/deployserver/config/)` (:13-28).
- **False success:** the `echo $(cp …)` wrapper always returns 0, so a failed copy into the **live** DS config still prints success (:26-28). Duplicate lines are never de-duplicated.

### backstage.sh (110, R) and vpenv.sh (111, read as a diff against vpenv_quiet.sh, which 02 read fully; the only extra is printing)
- **DS:**
  - WorkFlowSetter: `setprod P F; backstage.sh workFlowSetter TYPE "CRON"`, validator `has been updated to new value` (actions.xml:753-759).
  - SolrIndexSync: `backstage.sh index.sync -c jb -f mes -s mes -n 20000`, validator `BUILD SUCCESSFUL` (1389-1395).
  - GenerateSmartExpansions: `backstage.sh produce.files OPT [overwrite]`, validator `BUILD SUCCESSFUL` (1521-1531).
  - Also used by dtsGetter.sh and dtsSetter.sh.
- **Steps:**
  - `vpenv.sh` checks the required env and exits 55 if it is missing (:11-22).
  - The JVM args come from `deployconf.py jvmargs` (jmx and GC-print flags stripped) (:27, :41). It adds `-Did.legacy`, `-Dserver.type=rbackstage` when env.py says so, and `-Djdk17=yes` (:59-102).
  - `mkdir log` in the **current directory** (:106).
  - Runs Ant `-buildfile ~/scripts/conf/backstage.xml <target>` through the ant launcher (:107-110). The exit status is Ant's.
- **Notes:**
  - `BUILD SUCCESSFUL` covers every Ant target the session ran.
  - The SolrIndexSync arguments are hard-coded (collection `jb`, `mes`, 20000), not taken from the UI.

### dtsGetter.sh (107, R) / dtsSetter.sh (83, R): DtsGetter / DtsSetter
- **DS:**
  - DtsGetter: `dtsGetter.sh -p P -f F -t T -d <true|false>`, validator `disabling the DTS for` (actions.xml:760-765).
  - DtsSetter: `dtsSetter.sh -p P -f F -t T`, validator `BUILD SUCCESSFUL` (766-771).
- **Getter:**
  - Reads the DTS workflow schedule from the DB. The query invocation lines :81-85 are secret-bearing.
  - Saves it to `~/personal/dts_directory/P_F_dtsValue.txt` (:57-60).
  - With `-d true` it runs `backstage.sh workFlowSetter cliDtsSetter clear`, then prints `disabling the DTS for P done successfully` (:62-70).
  - Attaches the file to Jira (:72-76).
- **Getter failure paths:**
  - **With `-d false` the validator string is never printed**, so DtsGetter is **always Failure** even though the value was saved.
  - An empty DTS value prints `there is no DTS value…` and exits 0: Failure (:87-92).
  - After a failed clear it does a bare `exit` (0) (:65-67).
- **Setter:**
  - Loads the saved file and runs `backstage.sh workFlowSetter cliDtsSetter "<value>"`. The DS keys on Ant's `BUILD SUCCESSFUL` (:51-65).
  - A missing directory or file makes a bare `exit` (0) without the string, so Failure (:45-48, :69-71).

### major_upgrade_post_actions.sh (90, R) + setup_literatum.sh (143, R): SetPatchRelease / MajorUpdateLiteratumProps / CreatePatchPlan
- **DS:** `major_upgrade_post_actions.sh -b REL -a upgrade_patch|update_props|patchplan`. Validator: `COMPLETED SUCCESS` (actions.xml:1223-1240).
- **upgrade_patch:**
  - `setup_literatum.sh -r literatum-patch -b master` clones or pulls `~/sourcegit/literatum-patch-worktrees/master` (`set -e`; https first, then ssh) (setup_literatum.sh:51-97).
  - Then, for each of `mssql/{common,archive,literatum,report}/*.sql`, it `sed -i`s `@release_parm='trunk'|'HEAD'` to the new branch (:12-25).
  - The `exit 1` at :21 runs inside a `| while` subshell, so a sed failure does not stop the script.
  - **`git commit -m …` at :27 has no pathspec, `-a` or `git add`.** The sed edits are unstaged, so the commit should fail with "no changes added to commit", and the script exits 1. As written, SetPatchRelease cannot print `COMPLETED SUCCESS` unless changes were already staged. **Confirm against a real SetPatchRelease log** before relying on this.
- **update_props:**
  - `setup_literatum.sh -r literatum -b REL` creates the worktree `~/sourcegit/literatum-worktrees/REL`.
  - Then it runs `xmlstarlet ed -u properties/set[@name='macro']/set[@name='build']/string[@name='branch'] -v REL literatum.props.xml`, commits the file by path and pushes (:34-52). Correct.
  - Edge case: if the props node were renamed, `xmlstarlet ed -u` would match nothing and still exit 0. The file would be unchanged, so the later `git commit` fails on "nothing to commit" and the script exits 1. That fails safe; it is not a false success.
- **patchplan:** in `~/scripts/patchplan/` (platform-tools itself) it does `git reset --hard origin/master && git pull`, copies `patchdependency_trunk.xml` to `patchdependency_REL.xml`, and adds, commits and pushes it (:54-69). Checked at every step.

### v-index.sh (74, R): VIndex
- **DS:** `v-index.sh -p P -f F -t N -F FILE -u URL -T TENANT -g LOGDIR -b T [-i] [-d]`. Validator: `Ran successfully` (actions.xml:1241-1253).
- **Steps:**
  - Moves `~/reprocess/deployserverUploads/FILE` into LOGDIR. A missing file only prints `Dois file cannot be found…` and **continues** (:55-61).
  - `setprod`, then `run tool script -Dscript=VIndexOpTool.java -Dargs=…` (:64-65).
  - Prints `Ran successfully` when `$?` is 0 (:67-69), then attaches the newest `transform_failure_*.log` (:71-74).
- **False success:** `run` returns run.sh's code, and run.sh's env guards `exit` 0 (02 §2.7). A failed `setprod`, or a missing DOIs file that the Java tool tolerates, still gives `Ran successfully`. Per-DOI failures go to `transform_failure_*.log` and do not affect the verdict.

### updateSamlData.sh (36, R): ReloadSamlData
- **DS:** `~/scripts/updateSamlData.sh -f NAME`. Validator: `Done successfully` (actions.xml:1484-1489).
- **Steps:** looks up the URL for `NAME.xml` in `~/scripts/shibboleth/DownloadSAML_FedData.properties`, downloads it with `curl`, requires HTTP 200 (:25-29), and runs `mv -f` into `~/webdav_directories/samldata`, checked (:35-37).
- **Weakness:** the downloaded content is never validated (compare installSamlData.sh), so a 200 carrying an HTML error page is installed as SAML metadata.

### installSamlData.sh (186, R): InstallSamlData
- **DS:** `installSamlData.sh -f FILE -p P -t T [-o | -u URL]`. Validator: `Done successfully` (actions.xml:1630-1643).
- **Steps:**
  - Validates the XML: well-formed, and against the SAML 2.0 metadata XSD. `wsfed` namespace errors are ignored (:56-83).
  - On first run it downloads the XSDs from oasis-open.org and w3.org (:85-91).
  - Moves the uploaded file (`~/personal/reprocess/deployserverUploads`) or the downloaded one into `~/webdav_directories/samldata` (:93-138).
  - Runs a duplicate-content md5 check (:141-157) and links the file under `samldata/<P>/` (:160-161).
  - With `-u`, appends to the platform-tools `shibboleth/DownloadSAML_FedData.properties` and runs git commit and push from `~/scripts` after `git reset --hard origin/master` (:164-180).
- **Partial state:** the duplicate check runs **after** the file was moved into place. On a duplicate the script exits 1 but leaves the new file in `samldata` without the product link (:152-155).
- **Bug:** `/tmp/$ticket_$fileName` uses the undefined `$ticket_`, so it becomes `/tmp/$fileName` (:122-131).
- **Exit status:** `[[ $? == 0 ]]` at :182 sees the status of `git push`, or of the `if` in the upload path. It is not a false-success path.

### hbs_detector.sh (106, R): HBSDetector
- **DS:** `mkdir -p /tmp/hbs; hbs_detector.sh -p P -f F -t HOURS -i /tmp/hbs/<actionId>`. Validator: `EXECUTION SUCCESS` or `File is empty or contains Headers row only` (actions.xml:1595-1602).
- **Steps:**
  - `run tool script -Dscript=SubmittedHandlebarsReport.java -Dargs=\"H PATH\" | tee /tmp/hbs/tool_output_<ts>.log` (:88).
  - `grep "BUILD SUCCESS"` prints `EXECUTION SUCCESS` or `EXECUTION FAILED` (exit 1) (:90-95).
  - If the CSV has more than 1 line it creates a Jira LIT Task through `createNewTicket` and attaches the CSV (:23-31, :97-104).
- **Verdict:** it correctly uses Ant's text rather than the exit code. A failed Jira ticket creation is not checked; the action is still Success.

### escaped_revisions_cron.sh (110, R): ReportEscapedRevisions
- **DS:** `setprod P F; escaped_revisions_cron.sh`. Validator: `ReportEscapedRevisions done successfully` (actions.xml:1933-1939).
- **Steps:**
  - It must run on a `*-bks*` host after setprod (:82-90).
  - The SQL (:8-38) finds revisions the mass-removal queue skipped. The query and backstage invocation lines are secret-bearing (:44-45, 55-56, 92-96).
  - It writes `/archive3/literatum/webdav_directories/atyponops/DB/escaped_revisions_logs/P_USER_F_<date>` (:43-46).
  - It fails only if the backstage output contains `Java Result: 1` or `exception` (:57).
- **False success:**
  - "No rows" returns 0, so it prints the success string (:47-51). That covers a query that failed and produced an empty `dois.txt`, because the query's exit code is not checked at :44-46.
  - On success it `rm -rf ${filename}*`, deleting the report and the backstage output (:103-104). Nothing is left to inspect afterwards.

### deployConfValidation.sh (81, R): DeployConfValidation
- **DS:** `~/scripts/deployConfValidation.sh -a ACCT -r REV`. Validator: `Validation has been completed` (actions.xml:2146-2151).
- **Steps:**
  - `cd ~/.litconfig; git reset --hard origin/main; git clean -fdx; git pull origin main` (unchecked) (:47-48).
  - `xmllint --schema deployconf.xsd deployconf.ACCT.xml` (:50).
  - If there is no `validates`: creates a P1 Jira ticket, sends email and Google Chat (:53-60).
- **False success:**
  - `Validation has been completed` is printed **unconditionally** (:61), so the DS action is Success even for an invalid deployconf. The failure is reported only by the Jira ticket, mail and chat message.
  - `-r REV` is parsed and never used (:71-72). It validates `origin/main` HEAD, or a stale tree if the pull failed, not the revision under review.

### checkWebSiteAdminConfig.sh (215, R): CheckWebsiteAdminConfig / CheckConfGets
- **DS:**
  - CheckWebsiteAdminConfig: `-p P -f F -t T -i P-ACCT<fileId>`
  - CheckConfGets: `-a checkConfGets -p P -f F -t T -b HEAD -l PATH`
  - Validator for both: `BUILD SUCCESSFUL` (actions.xml:2164-2175).
- **Default path:** `setprod`, then `run tool script2 -Dscript=websiteAdminConfigChecker.java | tee /dev/tty`, then slices the summary between `summarized :` and `All Done!`, writes `/tmp/<fileId>{,_sum}.log` and attaches both to Jira (:139-169).
- **checkConfGets path:**
  - Runs `git reset --hard; git pull` (or `svn up`) **in `$ATYPON_HOME`**, the product's source worktree (:63-69). That can revert the LIT-656000 build-time patch from 02 §3.3 on a build host.
  - Greps the code for Conf/registry lookups (:70-76), dumps the registry through `RegistryQueryCli`, and queries `pb_change_set_widget_property` through `$DB_CONNECTOR` for marlin, demo, pericles and ux3 or for P (:84-104).
  - Reports path counts to Jira (:105-134). Without `-l` it does a bare `exit` (0) (:49).
- **Verdict:** Ant's `BUILD SUCCESSFUL`. On the checkConfGets path that comes from `RegistryQueryCli`, which runs only when `-p` is given. All Jira calls are sent to `/dev/null`.

### host_test.py (123, R): HostWarmupTest / HostEssentialTest / HostTest
- **DS:** `host_test.py -p P -f F -m HOST -t warmup|essential|<group> -i ACTIONID -a ACCT` (DS:`visitor/SshExecuteVisitor.java:849`; the group comes from :853-866; the path is chosen at runTest :576-580).
- **Steps:**
  - Reads the host IP, the product SSL port and the hostname from `~/.litconfig/deployconf.ACCT.xml` (:41-60).
  - `git pull origin master` in `~/sourcegit/qa-automation-xml`. A `cannot lock ref` error is tolerated, anything else gives `sys.exit(1)` (:64-82).
  - The docker image tag is the `pom.xml` `<version>` (:13-23).
  - **warmup:** `docker run … TESTNGSUITE=WARMUP … us-central1-docker.pkg.dev/atypon-artifact/docker-registry/qaa/xml-master:<tag>` (:89-92).
  - **Otherwise:** a FUNCTIONAL suite on the LambdaTest Chrome grid `selenium-grid-test.qaa.atypon.com`, then `docker cp …:/allure-report /tmp/results/<id>`, zip (:95-118).
  - Always ends with `docker rm -f` (:121-123).
- **Verdict (DS side):**
  - The first line containing `***Test Is Succeeded***` or `***Test Is Failed***` decides. Those strings are **printed by the test container**, not by host_test.py (DS:`visitor/SshExecuteVisitor.java:682-700` for warmup, ~714-726 for essential/HostTest).
  - host_test.py ignores every `subprocess.call` return code. A docker pull or run failure just produces neither string, so Failure.
  - No false-success path in host_test.py itself.
- **Note:** the warmup container gets no `ACTION_ID` (compare :90 with :101).
- **Reading coverage:** I skimmed the DS runTest body (SshExecuteVisitor.java:575-848). It is outside platform-tools.

### 2.2 DB clone / PB / docker DB / reprocess / non-web-instance set (fork A)


#### do_clone.sh (759 lines)

**DS callers** (`SshExecuteVisitor.java:1102-1149`; the command is always `cd ~/scripts; do_clone.sh -s SRC -t TRG -n SRCHOST -g TRGHOST -p PORT [-o …]`):

| Action | Mode | Success string |
|---|---|---|
| DbClone | full flow | needs both `Backup was done successfully` and `Restore was done successfully` |
| DbCloneBackup | `-o backup_only` | `Backup was done successfully` |
| DbCloneCopy | `-o copy_only` | `Copy Was successful` |
| DbCloneRestore | `-o restore_only` | `RESTORE DATABASE successfully processed` |
| DbCloneRemove | `-o remove_only` | `REMOVE_DataBase has done successfully` |

**Steps:**
1. Sets up `LOG=/tmp/do_clone_<ddmmyyyyHH>_$$.log` and the hard-coded server, port and drive tables (:12-33).
2. Guards (:587-615):
   - required args
   - target is `_live`/`pub_common` → exit 5
   - src == trg → exit 6
   - target must end `_Beta/_Stag/_ro/_RoReh/*_lts*/*_QA*/*_mig*`, unless the action is a backup → exit 7
3. Unless `-m DEV`: needs `/atypon/scratch` mounted and takes a global lock file `/atypon/scratch/personal/do_clone.sh_lck`. If the lock exists it prints `Someone else is working on the script…` and exits 20 (:622-641).
4. `set_var` (:97-133):
   - The target server comes from `list.py -E | grep -i TARGETDB | head -n1` (a substring match; the first hit wins). It falls back to `-g`.
   - It then builds the sqsh connection variables.
5. Unless backup_only:
   - `check_storage_volume` runs `xp_cmdshell 'sdcli snap list'`. A flexclone volume → exit 10, "use do_dbflexclone" (:181-196, 645-653).
   - `check_sessions` (sp_who2 count). Any session on the target → exit 8, listing the sessions (:199-258, 654-667).
6. Modes (:670-722):
   - `backup_only`: `backup_db` runs `BACKUP DATABASE … COPY_ONLY … COMPRESSION` via sqsh. Success means the output contains `BACKUP DATABASE successfully processed`; it then prints `Backup was done successfully` (:272-284).
   - `copy_only`: `copy_db_to_test`.
   - `restore_only`: `restore_db`.
   - `remove_only`: `remove_db`.
   - `backup_upload`.
7. Full flow (:725-753): backup (conditional, see below), then copy if the servers differ, then `restore_db`.
8. `copy_db_to_test` (:312-381):
   - Starts a PowerShell `Start-Job cp` through xp_cmdshell in the background.
   - Polls `C:\temp\copylog_*.txt` every `SLEEPTIME` for `True`, `False`, `Backup_Not_Found` or `LogFile-Not-Found`.
9. `restore_db` (:406-532):
   - Single-user mode, then drops the existing target (:451-456).
   - Starts the RESTORE in the **background** (:458).
   - Polls the whole `$LOG` for `RESTORE DATABASE successfully processed` or `…terminating abnormally`.
   - Prints `Restore was done successfully`, then `post_db_restore` (recovery simple, shrink logs), then exit 0.

**Touches:** the SQL Server fleet (vsql/tsql/dsql), `/atypon/scratch`, `/tmp/backup_success`, Windows shares `\\SRC\X$\Backup`, and `list.py` (deployconf).

**Failure modes:**
- Stale global lock after a SIGHUP'd or killed run. `exit_fun` is the only place the lock is removed, so every later clone exits 20.
- Sessions on the target → exit 8.
- A server not in the hard-coded list → exit 4.
- **Copy loop has no timeout** (:341-380): if the PS job never writes True/False, it loops forever.
- **Restore loop** times out only if no `percent processed` line ever appeared within 3 h (:484). A restore that stalls after some progress loops forever.

**False-success / false-failure paths:**
- **Stale backup reuse:** `/tmp/backup_success` is one host-wide line, shared by every DB and user (:27, 284, 294, 516).
  - When it reads `0 <SRC>` (backup ok, restore not finished), the next full run **skips the backup** (:725-733).
  - `RETURNSTAT` is then empty, and `[[ "" -eq 0 ]]` is true, so it restores the **old** `.bak`.
  - The DbClone parser then lacks `Backup was done successfully` → Failure, even when the restore of stale data succeeded.
- `post_db_restore` errors are ignored, because it runs after the success print (:508-515).
- `remove_db` prints nothing when the drop fails silently. DbCloneRemove then fails, which is correct. The drop is issued without checking sqsh output.
- `main $@ | tee -a $LOG` (:759): the exit status is tee's. Irrelevant to the DS.

#### do_optimize.sh (130)

- **DS:** DbOptimize, `cd ~/scripts; do_optimize.sh -t DB -n HOST -p PORT`. Success is `DB optimization completed successfully`.
- **Steps:** a sqsh heredoc runs `exec dbo.indexdefrag` and `sp_MSforeachtable UPDATE STATISTICS` over filtered user tables (:50-78). Then `awk` over `$LOG` looks for lines matching `msg ` + `Level ` + `State ` (:113).
- **False success (:113-126):** success is simply the absence of SQL-Server-style `Msg … Level … State` lines. A sqsh connect or login failure (Open Client messages), `sqsh: command not found`, or a wrong server all print **`DB optimization completed successfully`**. `LIVEDBS` is defined (:15) but never checked, so live DBs are not blocked.

#### do_dbflexclone.sh (326)

- **DS:** DbFlexClone / DbReportFlexClone / DbArchiveFlexClone (actions.xml:845-868), `do_dbflexclone.sh -s -t -n -g -p <type.cmdSuffix>`. Validate `Congratulations!`.
- **Steps:**
  1. Arg check.
  2. For non-`literatum` users with `-g testsql`, the target is resolved via `list.py -E | grep -i` (:269-275).
  3. Live-DB and same-DB guards (:277-293).
  4. `set_var`.
  5. `check_sessions`, unless backup_only. Sessions → exit 8 (:298-314). An empty sqsh result is coerced to 0 sessions, so a failed session check lets the clone proceed (:212).
  6. Resolves `@@servername` for both servers (:316-317, secret-bearing).
  7. Runs `xp_cmdshell 'pwsh.exe -NoExit -Command "SnapCenter init; C:\IT\database\datacenter\scripts\dbflexclone.ps1 SRC SRCDB TRG TRGDB ACTION"'` on the target SQL server (:319-322).
- **The `Congratulations!` string is not in this repo.** It must come from `dbflexclone.ps1` on the Windows host (outside every repo we have). The script itself prints no verdict and has no lock.
- **Risks:**
  - `-NoExit` on a non-interactive pwsh.
  - The flexclone logic is invisible here, so a triage must read the ps1 output in the DS log.

#### do_kill.sh (491)

- **DS:** optional pre-step of DbFlexClone/DbReportFlexClone when `forceKillDbSessions` is set: `do_kill.sh -t TRGHOST -d TRGDB -p PORT -s softDrop -o do_kill_all`. No validator of its own; the same action validates `Congratulations!`.
- **Steps:** live-DB guard (:392-402), `set_var`, then `killAll_sessions softDrop` → `killerLoop` (:259-273):
  - `kill` every session on the DB
  - **`ALTER DATABASE … SET OFFLINE WITH ROLLBACK IMMEDIATE`**
  - output captured into a variable and **never printed or checked**
  - `exit 0` (:337-342)
- `hardDrop` is disabled (:343-349). The list/vlist/plist/kill/status modes are not used by the DS.
- **Silent failure:** a kill or offline failure leaves no trace in the DS log. Successful or not, the DB is taken **offline**, and the flexclone that follows must bring it back.

#### BackupPB.sh (107) / RestorePB.sh (8)

- **DS:**
  - PB2backup: `BackupPB.sh "P:F"` → `Backup has been successfully done`
  - PB2restore: `RestorePB.sh P:F restore /shared/pb2backup/backups/P/<name>` → `Restore has been successfully done`
  - PB2restoreLast: `RestorePB.sh P restore` (no family) → same string
  - RestorePB.sh just sources the env and runs `BackupPB.sh $@` (RestorePB.sh:8).
- **Steps:**
  1. `setprod P F || exit 1` (:28).
  2. Backup: `mkdir` the backup dir; prune `.pb2`/`.log` files older than 3 days and keep 14 (:48-59).
  3. Restore: pick the given file, or the newest `${P}_${USER}*.pb2` (:61-79).
  4. `webSrv` from `list.py -p P --mType web -f F`; empty → exit 3 (:81-82).
  5. `ssh -n $webSrv "setprod; grep pb2 props.files.* && run tool pb -Dargs='-b|-r … -m overwrite' || echo <PB not enabled msg>" | tee logFile` (:86).
  6. PB not enabled → exit 23 (:88).
  7. Backup only: the `.pb2` file must exist (:90-93).
  8. `errorCount = grep -c "[java] Error\|Failed to restore"`. If it is 0 it prints the success message (:95-107).
- **False success:**
  - **Restore** has no artifact check. It reports `Restore has been successfully done` whenever the log lacks those two strings:
    - the ssh connection failed (log holds only the ssh error)
    - `run tool` hit its bare-`exit` env guard (exit 0, no output)
    - Ant ended `BUILD FAILED` with some other error text
  - **Multi-product** (`P1,P2`) loops and ends with a bare `exit` (:13-23). One product's success line satisfies the DS even when another failed.
  - PB2restoreLast passes no family, so `setprod P ""` and `list.py -f ""` are ambiguous on multi-family hosts.

#### docker/build_docker_db_wrapper.sh (207)

- **DS:** BuildDockerDatabaseImage (`-p -f -v <litBranch> [-i]`), BuildDockerDatabaseImageFromBackup (`-p -f -v -b`), UpdateDockerDatabaseFromBackup (`-p -f -b`). The command is `cd ~/scripts/docker; ./…`. Validate `DONE SUCCESSFULLY`.
- **Steps** (all through `~/apps64/ansible/inventory/ansible-actions.py -s mssql` — outside this repo; exit code checked, `printErrorMsg` → `ERROR: …` exit 1):
  - `-b`: prepare-product-database-from-backup, then daily-patch, then backup (:134-154).
  - Major (no `-i`): HTTP code of the Artifact Registry backup URL (`curl --write-out`) (:122-132).
    - `404`: prepare-product-mssql, then daily-patch, then backup.
    - Anything else: `start`, which pulls. This includes 401, 403, `000` and network errors.
  - Minor (`-i`), 200 (:156-172):
    - If the MR container is already running: print `… is exist.` and **`exit 0` without `DONE SUCCESSFULLY`** (:165-166). This is a false Failure.
    - Otherwise pull.
  - Minor (`-i`), non-200: `backupMinorBranch`, which starts the major, backs up the minor, then **unchecked** `docker stop/rm/volume rm` (:104-106), then starts the minor.
  - Finally `echo "DONE SUCCESSFULLY"` (:205).
- **Silent paths:**
  - An auth or network error on the registry check is read as "backup exists" → start/pull. It fails later if ansible reports it.
  - Docker cleanup errors are ignored.
  - Otherwise the verdict is only as good as the ansible-actions exit codes.

#### reprocess/submit_reprocess.sh (180)

- **DS:** SubmitReprocess (`cd ~/scripts/reprocess; ./submit_reprocess.sh -p -f -t -s -o -c -i [-e 22|20] [-O -a -b] [-I file]`, `SshExecuteVisitor.java:330-362`).
  - Success: `Submitting is done.` or `List of documents that haven't been indexed is (0). Exit reprocess submitting.`
  - The second one also **cancels the sibling CheckReprocess** (`SshExecutedVisitor.java:158-166`).
- **Steps:**
  1. `mkdir ~/personal/reprocess/<user>/<id>`. If it already exists → `ERROR` + `Failed To Complete.` (:34-42).
  2. Delta: `backstage.sh index.sync … >> list_arguments.log`, then read `Missing ratio:` (:52-72).
  3. Or `mv ~/personal/reprocess/deployserverUploads/<file> .`, unchecked (:73-78).
  4. `backstage.sh submit-reprocess <params> | tee /dev/fd/2` (:80).
  5. If the output contains `Submitting is done`, Jira `addComment "Submitting is done."`; else `Submitting is failed.` + `Failed To Complete.` (:86-91).
- **False success / inconsistency:**
  - When the missing ratio is `0.0%` it prints `List of documents … is (0). Exit reprocess submitting.` but **does not exit** (:64-71). It goes on to submit a reprocess anyway. The DS marks Success and **cancels CheckReprocess**, so that reprocess is never monitored.
  - If index.sync failed, `checkOutput` is empty and it submits with a possibly missing `missing_indexing_doi_list.log`.
  - `printErrMsg` ends with a bare `exit`, which is status 0 (:28-32). Irrelevant to the DS.

#### reprocess/check_reprocess.sh (322)

- **DS:** CheckReprocess (`./check_reprocess.sh -i ID -p -f -t [-a] [-b]`, `SshExecuteVisitor.java:365-387`, `blockIgnore`).
  - Success needs `Attached reprocessing report is done` and `SUCCESS: reprocessing completed` (with at least one more line after both), or `Found no content to submit`.
  - `Failed To Complete.` → Failure.
  - Anything else → Failure plus **one reschedule**.
- **Steps:**
  1. `cd ~/personal/reprocess/<user>/<ID>`. A missing dir → `Failed To Complete.` (:309-316).
  2. `backstage.sh check-reprocess`, then parse `[PROCESSING] N` (:28-39).
  3. Poll loops with 15/30/60/120-minute sleeps until N == 0 (:41-98).
  4. `getReprocessReport`: zip `<P>_inplace_*.log` and attach it to Jira (:147-179).
  5. `finalizeReprocess`: an `index` option triggers `runMergeIndices` (30 min sleep, then index.sync or solrV report) (:124-140, 181-272).
- **False success:**
  - `finalizeReprocess` prints **`SUCCESS: reprocessing completed` unconditionally** (:139). Index merge and report errors are ignored.
  - `Attached reprocessing report is done` is also printed when the report was >50 MB and only a Jira **comment** succeeded (:174 tests `addComment`'s `$?`).
- **Hangs:** if `backstage.sh check-reprocess` starts failing mid-loop, `processingContent` becomes empty, `[ "" -eq 0 ]` errors (false), and the loop **never ends** (:94, :78).
- **Minor bugs:**
  - `idDeployed` says "sleeping 5m" but sleeps 10m, and its error text is "is exists" (:111-121).
  - `runMergeIndices` parses the branch from `ATYPON_HOME` field 6. For `master`, or a path of different depth, `-ge 1910` errors and it falls back to the legacy solrV report (:186-191).
  - `indexFlag` is unset on the "already completed" path, so the merge is skipped (:133-136).

#### reprocess/digital_object_reprocess.sh (285)

- **DS:** DigitalObjectReprocess (`./digital_object_reprocess.sh -p -f -t -s -o -i -a … [-D]`, `SshExecuteVisitor.java:274-294`).
  - First match wins: `No dois to reprocess.. Exiting` / `BUILD SUCCESSFUL` → Success; `BUILD FAILED` / `Build failed, please check list_arguments.log for more info.` → Failure.
- **Steps:**
  1. Create the project folder (:35-44).
  2. Build the DOI list. Delta: `backstage.sh index.sync -c DO … -l do.txt >> list_arguments.log` (:56-73). Otherwise: sqsh bcp from the product DB into `do.txt` (:46-54).
  3. If `do.txt` is non-empty: `backstage.sh cli-reprocess >> list_arguments.log`, then `grep "BUILD SUCCESSFUL" list_arguments.log` and echo it (:216-224).
  4. `checkReprocess`, then an index.sync report (:109-183).
- **False success:**
  - **Delta mode:** `list_arguments.log` already holds the **index.sync** run's `BUILD SUCCESSFUL` (appended at :59/61). The grep at :220 therefore passes even if `cli-reprocess` failed, and the echoed line makes the DS say Success.
  - Non-delta: a failed sqsh or bcp (wrong server from xmllint, bad credential) leaves `do.txt` empty → `No dois to reprocess.. Exiting` → DS Success (:216-227).
  - A failed index.sync in delta mode leaves no `do.txt` → the same "No dois" Success.
  - The DS stops at the first `BUILD SUCCESSFUL`, so later `Failed To Complete.` lines from the check stage are ignored.
- **Dead monitoring:** `isDone output` passes the literal string `output`, not `$output` (:113). `processingContent` is empty, and `[[ "" -eq 0 ]]` is true, so it always prints "Reprocessing is already completed" and never waits (:116-174).
- `largeReportsPath` uses an undefined `$account` (:275). The getopts string `…D.a:` declares `O` but no `O` case is reachable (:234).

#### reprocess/passport_content_reprocess.sh (422)

- **DS:** SubmitPassportReprocess / PassportDigitalObjectReprocess (`./passport_content_reprocess.sh -s submit …`) and CheckPassportReprocess (`-s check`) (`SshExecuteVisitor.java:205-326`).
  - Success on `BUILD SUCCESSFUL` or `No dois to reprocess.. Exiting`; failure on `BUILD FAILED`.
- **Steps:**
  1. `isDeployed`: a missing webapp → `BUILD FAILED` (:326-333, 401).
  2. Submit: folder, `generateDOIsList` (DO via index.sync or sqsh bcp; JB via index.sync or `passport.list.cgs` / `passport.cli.ng`), then `submitReprocess`. DO uses `passport.cli.reprocess` and greps for BUILD SUCCESSFUL. JB uses `passport.process`, then `checkErrorsReport` (BatchId, `passport.process -berr`), then greps BUILD SUCCESSFUL (:31-202, 315-324).
  3. Check, DO: sleep 15 m, then an index.sync report (:209-221).
  4. Check, JB: poll sqsh counts every 30 min, then **`echo "BUILD SUCCESSFUL"` unconditionally** (:222-239).
- **False failure:** the script prints `No DOIs to reprocess.. Exiting` (capital DOIs; :59, 103, 120, 154). The DS matches the case-sensitive `No dois to reprocess.. Exiting`, so a legitimate "nothing to do" run is a **Failure**.
- **False success:**
  - CheckPassportReprocess JB: when the sqsh count query fails, `incompleteCount` is empty, `[ -gt 0 ]` errors, and the loop ends → `BUILD SUCCESSFUL` (:229-237). Aborted counts never cause failure.
  - CheckPassport DO prints only backstage's own index.sync output. Its `BUILD SUCCESSFUL` passes regardless of the reprocess result (:215).
  - JB submit: `checkErrorsReport`'s `backstage.sh passport.process -berr` output (with its own `BUILD SUCCESSFUL`) reaches the terminal before the log grep (:188, 323). Batch errors are listed but still Success.
  - `generateDOIsList`'s `return 1` is ignored by `main` (:408).
- Other bugs: `${jiraId}` is undefined (:57); `usage` is undefined (:225); in check mode `cd $reprocessProjectPath` with an empty var goes to `$HOME` (:210, 223).

#### add_remove_Non_web_instance.py (348)

- **DS:**
  - AddNonWebInstance: `cd ~/scripts/; ./add_remove_Non_web_instance.py -p P -i backstage|rbackstage -t T -a add -c`. Failure on the first line containing `ERROR` or `error`; Success on `The rbackstage server [host]`, whose host feeds sibling actions.
  - FinalizeReprocess (actions.xml:1950-1956): `setprod; rstrt -q; …py -p -t -a remove -c`, validate `Removing the rbackstage done successfully`.
- **Steps:**
  1. **Parses `~/deployconf.xml` first** (:288-289).
  2. `list.py | grep` product check (:317-320).
  3. With `-c`, `checkDiff`, then `updateDeployConf`, which runs `cd ~/.litconfig && git reset --hard origin/main && git clean -fdx && git pull origin main` (:179-194, 325-327).
  4. add: `getProductRbackstageServer` prints `The rbackstage server is [<prefix>-prod-rbks1]` (prefix = product for tier 1, DB-name prefix for tier 2), then `addRbackstage` inserts `<machine><process name="rbackstage"/>` after the backstage machine (:161-176, 50-63).
  5. remove: deletes the ticket comment and **every** rbackstage machine of the product (:66-75).
  6. `root.write`, then `git commit`, then an **unchecked `git push`**, then `SUCCESS: Commited …` (:197-209, 339-341).
- **Deployconf clobbering:** the tree is parsed *before* the reset/pull. Writing it back overwrites whatever the pull brought in, so the commit can **revert concurrent deployconf changes** (:289 vs :327, :339).
- **False success:**
  - Add: the success marker (:175) is printed before the edit. An exception whose text lacks `error`/`ERROR` still ends as Success, with the deployconf untouched. Examples:
    - `AttributeError: 'NoneType' object has no attribute 'get'` when a machine has no `<process>` (:57)
    - `KeyError` / `UnboundLocalError` (capital `Error` only)
  - Remove (FinalizeReprocess): the validate string is printed before `write` and commit (:75). A commit or push failure after it still leaves the action Success.
  - The push result is never checked (:206-209). A failed push is Success for FinalizeReprocess, and a Failure for Add only because git prints `error:`.
- `-i` is only validated; add always inserts `rbackstage`, even when the DS passes `backstage` for non-literatum accounts (:235-239, 52-54).
- `accountsNamesDic[getuser()]` gives a KeyError for any other account, for example cip (:182-185).
- `getServersWithLowestLoad` / `getLowestServerUsage` are dead code (:78-159).

#### processing_scripts/reprocess_LIT-516738.py (111)

- **DS:** CustomReprocessProduct (actions.xml:1941-1948): `setprod; cd ~/scripts/processing_scripts; ./reprocess_LIT-516738.py -p P -a ACCOUNT -t T`. Validate `CustomReprocess done successfully`.
- **Steps:**
  1. Parse `~/.litconfig/deployconf.<account>.xml`. It needs a machine whose process is `backstage`; the message says "rbackstage" (:36-61).
  2. For 2 pubAgentTypes × 2 areas, a sqsh query writes DOIs to `~/tmp/<…>.txt` (:64-91).
  3. For each file: `backstage.sh cli-reprocess … -s kbadarneh@atypon.com …` (a hard-coded personal submitter), or `passport.process` for passport products. `subprocess.run(check=True)`. `Java Result: 1` → exit 1; otherwise it prints `CustomReprocess done successfully` (:93-107).
- **False success:**
  - The success line is printed **per file**. A later file failing (CalledProcessError traceback, or `Java Result: 1`) leaves the earlier line in the log → DS Success.
  - A failed query gives an empty DOI file, reprocessing of nothing, and Success.
  - `BUILD FAILED` is not checked.
- Bugs:
  - `returnCode + bcolors.ENDC` raises a TypeError on a failed query (:80).
  - `accountEngineMap` covers only staging and literatum, so there is a KeyError elsewhere (:40, 95).
  - `~/tmp` must exist (:67).

---

### False-success rows

| Script:line | Mechanism | DS action | Effect |
|---|---|---|---|
| do_optimize.sh:113-124 | Success = no `Msg/Level/State` lines; connect failure or missing sqsh passes | DbOptimize | "DB optimization completed successfully" with nothing optimized |
| do_clone.sh:725-747, 27 | Host-wide `/tmp/backup_success` state skips the backup; empty RETURNSTAT treated as 0 | DbClone | Restores a **stale** `.bak`; DS shows Failure (no backup line) even though the restore ran |
| do_clone.sh:341-380, 484 | Copy poll has no timeout; restore times out only with 0 % progress | DbClone / DbCloneCopy / DbCloneRestore | Action hangs until the DS kills it |
| do_clone.sh:15, 631 | Global lock removed only by `exit_fun` | all do_clone actions | Stale lock → every clone exits 20 |
| do_kill.sh:259-273, 342 | Kill + OFFLINE output captured and never checked; `exit 0` | DbFlexClone (force-kill) | Silent; DB left offline if the flexclone then fails |
| do_dbflexclone.sh:212, 319-322 | Empty session count → 0; verdict string comes from a ps1 outside the repo | DbFlexClone* | Proceeds with live sessions if the check fails; verdict opaque |
| BackupPB.sh:86-107 | Restore success = absence of 2 strings; no artifact check; ssh/`run tool` failure passes | PB2restore / PB2restoreLast | "Restore has been successfully done" with nothing restored |
| BackupPB.sh:13-23 | Multi-product loop; any product's line satisfies the DS | PB2backup / restore | Partial failure reported as Success |
| build_docker_db_wrapper.sh:165-166 | `exit 0` without `DONE SUCCESSFULLY` when the MR container exists | BuildDockerDatabaseImage -i | False **Failure** |
| build_docker_db_wrapper.sh:124-131 | Any non-404 registry code (401, 000) treated as "backup exists" | BuildDockerDatabaseImage | Wrong branch taken; relies on ansible failing |
| submit_reprocess.sh:64-71 | "(0) … Exit reprocess submitting." printed without exiting; reprocess still submitted | SubmitReprocess | Success, and the DS **cancels CheckReprocess**, so the submitted reprocess is unmonitored |
| check_reprocess.sh:139 | `SUCCESS: reprocessing completed` unconditional | CheckReprocess | Merge/index errors hidden |
| check_reprocess.sh:174 | "Attached … done" keyed on addComment `$?` for >50 MB reports | CheckReprocess | Success with no attachment |
| check_reprocess.sh:78, 94 | Empty count → test error → infinite poll | CheckReprocess | Hang |
| digital_object_reprocess.sh:59/61 + 220 | index.sync's `BUILD SUCCESSFUL` already in list_arguments.log satisfies the cli-reprocess check | DigitalObjectReprocess (delta) | Success when cli-reprocess failed |
| digital_object_reprocess.sh:216-227 | sqsh/bcp or index.sync failure → empty do.txt → "No dois" | DigitalObjectReprocess | Success, nothing reprocessed |
| digital_object_reprocess.sh:113 | `isDone output` (literal) → monitoring dead | DigitalObjectReprocess | Finishes immediately, never waits |
| passport_content_reprocess.sh:229-237 | Poll loop exits on a failed count query → unconditional `BUILD SUCCESSFUL` | CheckPassportReprocess (JB) | Success without completion; aborted items ignored |
| passport_content_reprocess.sh:215 | Only index.sync output; its BUILD SUCCESSFUL decides | CheckPassportReprocess (DO) | Success regardless of outcome |
| passport_content_reprocess.sh:188, 323 | `-berr` run prints BUILD SUCCESSFUL before the verdict | SubmitPassportReprocess (JB) | Batch errors → Success |
| passport_content_reprocess.sh:59,103,120,154 | Prints `No DOIs…`; DS expects `No dois…` (case-sensitive) | Submit/PassportDigitalObject reprocess | False **Failure** on "nothing to do" |
| add_remove_Non_web_instance.py:175 | Success marker printed before the edit; exceptions without `error`/`ERROR` text pass | AddNonWebInstance | Host assigned in DS, deployconf not changed |
| add_remove_Non_web_instance.py:75, 206-209 | Validate string printed before write/commit; push unchecked | FinalizeReprocess | Success with the deployconf change not pushed |
| add_remove_Non_web_instance.py:289 vs 327, 339 | Tree parsed before git reset/pull, written back after | Add/Finalize with `-c` | Can revert concurrent deployconf commits |
| reprocess_LIT-516738.py:107 | Success line printed per file; later failures ignored | CustomReprocessProduct | Partial failure → Success |

### Coverage

**Read fully (13 files, 3,745 lines):**

| File | Lines |
|---|---:|
| do_clone.sh | 759 |
| do_optimize.sh | 130 |
| do_dbflexclone.sh | 326 |
| do_kill.sh | 491 |
| BackupPB.sh | 107 |
| RestorePB.sh | 8 |
| docker/build_docker_db_wrapper.sh | 207 |
| reprocess/submit_reprocess.sh | 180 |
| reprocess/check_reprocess.sh | 322 |
| reprocess/digital_object_reprocess.sh | 285 |
| reprocess/passport_content_reprocess.sh | 422 |
| add_remove_Non_web_instance.py | 348 |
| processing_scripts/reprocess_LIT-516738.py | 111 |

Caveat on "fully": the credential-bearing lines listed at the top were seen only as structure (variable names and `-S/-D` targets), never as values. A few usage-echo lines hidden by the `-p` filter in do_kill.sh (:34-60) were not seen.

**Not read:**
- Called but in this repo: `jira_funcs` (addComment/addAttachment), `backstage.sh`, `list.py`, `functions.sh`/`aliases.sh` (already covered in note 02). The other `reprocess/*` scripts are not called by these four.
- Outside this repo: `ansible-actions.py`, and the Windows `dbflexclone.ps1` that emits `Congratulations!`.

### 2.3 Ops / tooling set (fork B)


### Action → script table

| DS action (actions.xml line) | Command | Validator |
|---|---|---|
| AlertExternalEnable (772) | `cd /atypon/scratch/personal/shared/; ./pingdomApi.sh -a unpause -s P; catchpointApi.py -p P -c DeactivateMaint` | `unpausing` |
| AlertExternalDisable (787) | same, with `-a pause` / `ActivateMaint` | `pausing` |
| UpdateStatusPage (237) | `cd /atypon/scratch/personal/shared/; pingdomApi.sh -a unpause\|pause -s P` then opstool RundeckApiService; or `ansible-actions … status-page-incident` + AnsibleCheckExitCode | `COMPLETED SUCCESS` |
| PagerDutyShifts (1205) | `cd ~/scripts; python3 pd_shift.py --since --until --old-user --new-user [--skip-office-hours]` | `Successfully created` |
| MissingMerges (2742) | `python3 MissingMergeDetector.py SRC TGT AFTER BEFORE -t` (no `cd`) | `Done successfully` |
| VideoCodec (261) | `setprod P F; video_codec.sh -p SAMPLE -s STATUS` | `Task finished successfully` |
| CloudflareVideoAnalytics (2748) | `video_analytics_v1.py --account-id … --resultFile ID; addAttachment … &` | `Result generated under` |
| CloudflareVideosData (2755) | `stream_analytics_v2.py …; addAttachment … &` | `Result generated under` |
| CfVideosCleanup (1408) | `eval $cmd`, which runs **`deployserver_stream_bulk_delete.py`**, not `CF_video_cleanup.py` | `Videos cleanup Completed` |
| CloudFlareRecordAdd (2152) | `~/scripts/cloudflare-dns.sh -a add -n P-F --multisite` | `DNS record added successfully` |
| CloudFlareRecordRemove (2158) | `~/scripts/cloudflare-dns.sh -a delete -n P-F` | `DNS record deleted successfully` |
| EnableArgoTunnel (1575) | `enable_argo_tunnel.sh --target T -d DUR -p P -f F -b TICKET [-l DOMAIN]` | **none (always Success)** |
| SyncGitWithSvn (1718) | `~/scripts/svn_to_git_setup.sh ~/source` | **none** |
| GitBranchCreate (2026) | `~/scripts/cms/handle_cms_cut_branch.sh -p PARENT -b BR -t cms-root\|cms-ps-wiley\|cms-ps-elsevier -g` (non-major) | `Done successfully` |
| CreateCmsJenkinsPipelineFromTemplate (2043) | `~/scripts/cms/handle_cms_jenkins.sh -p -b -t TYPE -o template` | `Done successfully` |
| CreateCmsReleaseByJenkins (2075) | `~/scripts/cms/handle_cms_jenkins.sh -p -b -t TYPE -o release [-g]` | `Done successfully` |
| AtmTraining (2129) | `~/scripts/AutomateATM.sh -p P -b BR -j T -c PCT -n TOPICS` | `ATM has been finished successfully` |
| RunImageOptimizerTool (976) | `~/scripts/image_optimizer.sh P` (positional; no setprod) | `Finished at` |
| GatherProductWidgets (343) | `setprod P F; ~/scripts/generate_widget_report.sh TICKET` | `Product csv file created` |
| AnalyzeWidgets (356) | `~/scripts/analyze_widgets_report.py --name=TICKET` | `Excel Sheet Created` |
| UpdateCounterRobotsList (661) | `~/scripts/insightsops/UpdateCounterRobotList.sh` | `UpdateCounterRobotsList patch had been committed to git OR there is nothing to commit` |
| AddGitbotFeature (2776) | `checkoutGitRepo githubbot master; python3 ~/scripts/gitbot/addGitbotFeature.py -g -r -n -p -ht -t` | **none** |
| FirewallsReport (1478) | `~/scripts/puppet_workstation_report.sh -u USER` | `Report generated` |
| UpdateAtyponLifecycle (1686) | `~/scripts/updateMjrBranchesList.sh BRANCH` | `Updated MJR_BRANCHES_LIST` |
| ToolOpstoolInstall (1818) | `${HOME}/scripts/build_opstool.sh -r` | `Finished Successfully` |
| SyncWebdavSaml (1724) | `/bin/bash /na101/home/literatum/scripts/webdav_dr_saml_sync.sh` | `All syncs completed at ` |
| AnalyticsSyncEvents (893) | `ansible-playbook -i ~/scripts/analytics_events/env_hosts_inventory.py …/playbook.yaml -e test=no` | **none** |
| IamRedisCacheLoader (1927) | `${HOME}/scripts/operations/cron/pericles_culp_resync.sh` | **none** |
| PyroscopeProfile (2811) | `~/scripts/pyroscopeProfile.sh P MIN` | `PROFILING_TRIGGERED` and not `ERROR:` |
| UpdateYaegerVersion (visitor, `SshExecuteVisitor.java:410-427`) | `cd ~/scripts/; ./updateYaegerOnLiteratumBranches.sh -v V -t T -b <yaeger.branches>` | **no parser**: status becomes `Cancelled` |
| (TestUtils, `TestUtils.java:32-33`) | `cd ~/scripts/xmlqaauto; ./pull_deploy_xmlqaauto_jar.sh VER` | n/a (helper) |

**UpdateYaegerVersion is confirmed Cancelled.**
- `SshExecutedVisitor` extends `IActionVisitor.Noop`, whose `visitUpdateYaegerVersion` is empty (`IActionVisitor.java:4315`).
- `logParseStatus` starts as `Cancelled` (`SshExecutedVisitor.java:42`).
- There is no actions.xml entry, so `Action.Factory.inst` is null and the parser path is used (`DeployDaemonHelper.java:523-531`).
- Result: the action always ends **Cancelled**, whatever the script did.

---

### Per-script sections

#### pingdomApi.sh (564, read fully; ~/scripts copy)

- **Which copy runs:** AlertExternal* run `./pingdomApi.sh` after `cd /atypon/scratch/personal/shared/`, so they execute **the copy in that shared dir, not this repo's file**. That copy was not seen. UpdateStatusPage calls bare `pingdomApi.sh` after the same `cd`; which copy wins depends on PATH order (`.` is on PATH per note 02).
- **Setup:**
  - Sources `.bash_profile`, `.bashrc`, `functions.sh`, `aliases.sh` and `jira_funcs` (:3-7).
  - Takes a per-site lock with `lockfile -r 0 /tmp/theNew_<md5>.lock || exit 1` (:444, :496). A concurrent or stale lock exits silently, and the DS then fails for lack of the string.
  - `trap cleanup EXIT` (:497). `cleanup` always does `exit 1` (:432).
- **Main flow:**
  - Starts a timeout watchdog at 300 s, or 4 h for `all` (:8, :17-28, :513).
  - Fetches all checks with `pingdomApi.py -a getAll` (:516). The Python client is not in the list for this fork.
  - Runs `git -C ~/.litconfig pull` and `list.py` (:533-534).
  - For each product, `doAction` loops over the checks and matches by name, id, name-part, or product regex (:256-343).
  - pause: prints **`pausing check : <name>`** (:298), then `pingdomApi.py -a pause -i ID` (:198), whose result is **never checked**.
  - unpause: prints **`unpausing check : <name>`** (:302), then calls the API (:202).
  - `doAction` output goes to `$reportFile` (:547) and reaches the DS log through `cat $reportFile` (:554), because the action is not `outagesYstrdy all`.
- **Fail modes:**
  - No check matches the product: no `pausing` line.
  - Lock held.
  - The `pingdomApi.py` getAll failure is not checked. The list is then empty and no line is printed.
- **False success:** the "pausing/unpausing check" line is printed **before** the API call and regardless of its result (:298-303).

#### catchpointApi.py (152, read fully) + catchpoint.py (596, read with filter; auth lines removed)

- **Flow:**
  - `ActivateMaint`/`DeactivateMaint` → `ActivateDeactivateMaint` (:104-125).
  - Look up the product id (:65-77), then the maintenance schedule id (:80-89), then `scheduleStatus`, flip Active/Inactive, and `changeScheduleStatus` (POST).
  - Prints **`pausing/unpausing action is done`** (:125).
- **Product not found:** prints **`product not found .. skip pausing unpausing`** and `exit(0)` (:76-77).
- **Other failures:**
  - HTTP ≠200 raises `CatchpointError` (catchpoint.py:103-104), which produces a traceback.
  - A connection error runs `sys.exit(msg)` (catchpoint.py:43-45).
  - `prodsDic[name1]` gives a KeyError for any Catchpoint product name not in the dict before the match (:73).
- **Critical false success:** both strings contain **both `pausing` and `unpausing`**.
  - AlertExternalEnable (`unpausing`) and AlertExternalDisable (`pausing`) both **pass whenever catchpointApi.py reaches :76 or :125, even if the product was not found or pingdom did nothing**.
  - In addition, `pausing` is a substring of `unpausing`, so Disable also passes on an Enable-style line.

#### pd_shift.py (527, read fully)

- **Flow:** PagerDuty REST (api.pagerduty.com):
  1. user lookup by email (:23-37)
  2. all schedules, paged, plus per-schedule details (:39-86)
  3. rendered entries for since/until (:88-115)
  4. POST override per entry (:117-153), optionally split around 9-17 Asia/Amman office hours (:162-243)
- **Output:** always prints **`Successfully created {n} override(s)`** at the end of `create_shift_overrides` (:356), including **n = 0**.
  - Per-entry failures only print `Error: Failed to create override…` (:390, :405).
  - Entry fetch errors are swallowed into `Warning:` and `[]` (:113-115).
  - Some 400 errors are treated as `past_entry` (:139-149).
- **Correct failures:** early returns (user not found, no schedules) print `Error:` / `No schedules…` with no success string, so the DS marks Failure.
- **False success:** PagerDutyShifts passes with 0 overrides created, or with every override failing.

#### MissingMergeDetector.py (500, read fully)

- **Flow:**
  - SVN-only: `svn log --xml` on `https://svn-master.int.atypon.com/svn/{trunk|branches/X}` (:301-303, :345-349).
  - Matches `(merged from …)` annotations and diff-compares with `svn diff -c` (:78-101, :195-255).
  - Writes `missed_merges_*.xlsx` (:317-338).
  - With `-t`: creates a Jira Epic plus per-author tasks (:359-422, :480-491).
- **Output:** it **never prints `Done successfully`**; it ends with `Total time taken:` (:497). **MissingMerges can never pass the DS validator.**
- The DS runs `python3 MissingMergeDetector.py` with no `cd ~/scripts` (actions.xml:2744). Unless the shell cwd is `~/scripts`, this is `No such file`.
- It only understands SVN, so it is stale for git-era branches (≥2410).
- **Side effects before the DS failure:** Jira tickets are filed.

#### video_codec.sh (190, read fully)

- **Flow:**
  - Requires `PRODUCT_NAME` (:8-11) and `setprod` (:56).
  - Reads the registry `passport/enabled` via `run tool main RegistryQueryCli` (:58-66). The `$?` check at :59 is on the pipeline tail (awk), so it is effectively always 0.
  - LCMS: DB query for `publication` + `aux_info` paths (:72-85). PCMS (passport): `passport/source-root-relative-path` plus `lit_cloudflare_metadata where status=S` (:89-120).
  - Runs `ffprobe` + `_video_codec.py` per file (:124-160) and writes `/tmp/cflog_*.csv/.err`.
- **Output:** prints **`Task finished successfully`** unconditionally (:180), whatever the missing/error count `i` (:164).
- **False success:**
  - Every file missing or failing still passes.
  - An empty DB result (no paths) still passes.

#### video_analytics_v1.py (77, read fully)

- **Flow:** Cloudflare Stream analytics GET per video id, then CSV in cwd (:36-57). Prints `Result generated under …` only after all ids (:76).
- **Failures:**
  - A non-200 raises, but only **after** `json['result']` has been read (:46-49).
  - A missing `--videosIds` crashes at :71 (`None.split`).
- The DS then runs `addAttachment … &` in the background, so the attachment result is never checked.

#### stream_analytics_v2.py (175, read fully)

- **Flow:** lists all Stream videos (paged by `end`), then GraphQL view events. Prints `Result generated under` last (:176).
- **Failures:**
  - `get_videos` does not check the HTTP status (:120-122); an error body without `result` gives a KeyError traceback.
  - Correctly fails otherwise.

#### deployserver_stream_bulk_delete.py (151, read fully; the script CfVideosCleanup actually runs) / CF_video_cleanup.py (not referenced by the DS; not read)

- **Flow:**
  - Hard-coded Cloudflare account URL (:26).
  - Refuses without interactive confirmation unless the account name is `Atypon Development` (:38-42). In a DS shell, `input()` would consume the next typed DS line.
  - Lists videos, optionally filtered by `--product`, `--after`, `--before` (:63-95).
  - 10 daemon threads DELETE each uid (:98-124).
- **Output:** prints **`Videos cleanup Completed`** at:
  - queue empty at start (:131)
  - each worker's `queue.Empty` (:123)
  - main loop when `qsize()==0` (:148), after which the script exits
- **False success:**
  - Delete errors print `Error detected` and the uid is abandoned after 2 errors (:101-114). The run still "Completed".
  - The main loop prints Completed when the queue is **dequeued**, not when the deletes finish. Daemon threads are killed at exit, so the last ≤10 in-flight deletes can be cut off.
  - `--dry-run` exits silently (:138-139), so the DS reports Failure for a dry run.

#### cloudflare-dns.sh (296, read fully)

- **Flow:**
  - `set -euo pipefail` (:3), `source ~/.bashrc` (:20), GPG-decrypted config (secret lines filtered).
  - add: CNAME `<name>.cip` → `dc-lb-non-prod.literatumonline.com` (:13, :187), plus `*.<name>.cip` with `--multisite` (:190-194).
  - delete: `<name>.cip` then `*.<name>.cip` (:231-239).
- **Output:** `✓ DNS record added successfully: X` (:171) / `deleted successfully` (:221).
- **False success:**
  - With `--multisite`, the main record is added (string printed) and then the wildcard fails (`return 1`, script exits). **CloudFlareRecordAdd passes with no wildcard record**, so multisite hosts don't resolve.
  - On delete, a missing main record is skipped with WARN (:205-207) and the wildcard delete prints the success string.
  - A `get_record_id` API failure is masked by `local x=$(…)` (:203). The error JSON on stdout then becomes the "record id", and the DELETE fails. That one is a correct Failure.
- **Correct failures:** add of a record that already exists; delete when neither record exists (nothing printed).

#### enable_argo_tunnel.sh (292) + enable_argo_tunnel_functions.sh (65), both read fully

- **Logging:** `exec &>> /tmp/enable_argo_tunnel_logs/$USER/enable_argo_tunnel_<ts>.log` (:21). **All output goes to a host file; the DS log gets nothing.**
- **Flow:**
  1. `setprod` (:209)
  2. `get_product_info` gets the https port from `list.py` and maps the account to an env code; an unknown account does `return 1` (:117-167)
  3. `run tool manageArgoTunnelSecondaryDomain -Daction=create` (:228)
  4. `cloudflared tunnel create` + `route dns` (:104-115)
  5. `cloudflared … run &` (:237)
  6. cleanup scheduled with `at now + <duration> minutes` (:241): kill tunnel, `tunnel cleanup/delete`, delete the secondary domain (functions :52-65)
- **Error handling:** `exit_on_failure=false` (:72), so `run_command` failures print `Failed, ignore and continue` (:99). `cloudflared` create/route results are not checked (:106, :113). `tunnel_id` can be empty.
- **False success:** the action has no validator, so it is **always Success**. That holds even when:
  - the tunnel, domain or DNS failed
  - `at` is missing
  - the product has no https port (exit 2)
- A bad option does `return 1` at top level (:288), which is invalid outside a function.

#### svn_to_git_setup.sh (136) + svn_to_git_sync.sh (173), both read fully

- **Flow:**
  - Targets `~/sourcegit/HEAD` (literatum clone) and its `atypon/patch`, plus branches `lit-2410` and `lit-2210` (:3-7).
  - For each: `git pull`, `svn up`, then `svn_to_git_sync.sh`. That script runs `rsync -a --delete` from SVN into the git tree (sync:67-142), then `git add .; commit; git push` (sync:149-164).
- **Relative-path bug:** the branch loops and the clone path call **`./svn_to_git_sync.sh`** (:93, :95, :118-131). The DS runs the script from `$HOME`, so those calls are `No such file`. Only the trunk/patch calls in the update path use `$HOME/scripts/…` (:78-82).
- **Unchecked results:**
  - `git pull` / `svn up` (:69-75, :87-90)
  - `git push` (sync:162, then `Pushed to GitHub` is printed unconditionally)
- **Risk:** it pushes an `rsync --delete` of SVN state onto GitHub `literatum` master/lit-2410/lit-2210. If SVN is stale, this **reverts git history on those branches**.
- **False success:** no validator, so always Success. It prints `Operation completed successfully!` unconditionally (:136).

#### cms/handle_cms_cut_branch.sh (218, read fully)

- **Flow:**
  - cms-root: `checkoutGitRepoBranch cms-root`, then `mvn gitutil:branch` (creates the MR branch), then bump the parent pom patch version, `mvn versions:set/commit`, `git commit -a`, `git push origin` (:73-123).
  - ps-wiley / ps-elsevier: `git checkout -b MR`, then `-SNAPSHOT` → `.1-SNAPSHOT`, commit, `push origin MR`, back to parent (:125-177).
  - Output: `Done successfully`.
- **Exit status:** `checkResCode` does `exit $?` after an `echo`, so it **exits 0** on failure (:15-19, :47-68). The DS doesn't care, because `Done successfully` is absent.
- **Stale parent:** `git pull` after the checkout is unchecked (:78, :129, :156), so the branch can be cut from a stale parent.
- **Partial state:** on cms-root, gitutil can create and push the MR branch and then the parent bump fails. The DS shows Failure, but the branch exists.

#### cms/handle_cms_jenkins.sh (248, read fully; credentials seen, not reproduced)

- **template:** `curl GET …/job/maintainance/job/<parent>-…-MR-Template/config.xml` (on acjenkins.atypon.com), then `sed`, then `xmlstarlet` adds the MR branch to the choice list, then `curl POST config.xml`, then `Done successfully` (:21-50, :60-89, :99-128, :140-169).
- **release:** `curl POST …/buildWithParameters branch=MR git=<litOnGit>`, then `Done successfully` (:52-58, :91-97, :130-137, :171-178).
- **False success:** `curl` has **no `-f`**, so HTTP 401/403/404/500 still exit 0.
  - A failed config upload or build trigger prints **`Done successfully`**.
  - A 404 template download is caught only because `xmlstarlet` fails on the HTML body.
- `printErrMsg … "$?"` passes the status of the `[[ ]]` test (0), so the error exit is 0. That doesn't matter to the DS.

#### AutomateATM.sh (90, read fully)

- **Broken option parsing:** `getopts "h:p:c:n:t:j:"` has **no `b`** (:16), but the DS passes `-b ${branch}` second (actions.xml:2131). getopts returns `?`, which matches `?)`, so it prints usage and **exits 2 before doing anything** (:47-50).
- Even if it parsed, `$branch` (:73) is never set (the option would set `branch_number`, :44).
- Script paths are quoted with `~` (:55-59), which does not expand.
- It prints `ATM has been finished successfully` only if some `*.log` contains `seconds elapsed` (:91).
- **Net effect:** AtmTraining always fails.

#### image_optimizer.sh (106, read fully)

- **Arguments are ignored:** the DS passes the product **positionally** (actions.xml:978), but the script only reads `-p` (:75-79). `product=$PRODUCT_NAME` (:5), and the action does **no setprod**, so it is whatever the login shell has (likely empty).
- **Flow:**
  - `git reset --hard; clean; pull` or `clone` of image-optimizer (:19-30)
  - nvm 10.8.0 + npm globals (:36-60)
  - runs `~/sourcegit/image-optimizer/image-optimizer.sh` in `~/publisher/<P>/sda/assets` only if that dir exists (:67, :70)
- **Silent skip:** if the dir is missing, the step is skipped with no message.
- **Validator:** `Finished at` is not printed by this script. It comes only from the external repo's script, so a skipped run fails correctly. `PB_BKRESTORE=true` prints `skip` and exits 0 (:3), which the DS marks Failure.

#### generate_widget_report.sh (111, read fully)

- **Flow:** checks the Jira ticket (:58-63), then `run tool script -Dscript=~/scripts/AnalyzeWidget.java -Dargs=<csv>` (:97). A failed `run` is detected (:101-103).
- **Typo:** the final guard tests **`$jira_tickets_check`** (:110), but the variable set at :46 is `jira_ticket_check`. The guard is always false, so **`Product csv file created` is never printed and GatherProductWidgets always fails**, even when the CSV was produced.

#### analyze_widgets_report.py (143, read fully)

- **Flow:** reads `~/personal/widget/<ticket>/*.csv`, builds a shared/unique widget xlsx, uploads it to Jira, `rmtree`s the folder, then prints `Excel sheet created` (:143).
- **Case mismatch:** the DS validator is **`Excel Sheet Created`** (capital S and C, actions.xml:360). The match is case-sensitive, so **AnalyzeWidgets always fails**, even after the upload has succeeded and the input dir has been deleted.

#### insightsops/UpdateCounterRobotList.sh (79, read fully)

- **Flow:**
  - `cd ~/sourcegit/literatum-patch-worktrees/master; git reset --hard; clean; pull` (:15-16)
  - `curl -s` the COUNTER bots list over `data/CounterRobots/counter_robots_list.txt` (:60). There is no `-f`, so an HTTP error writes the error body into the file.
  - `isUpdated=$(svn st <file>)` (:68)
- **SVN check on a git worktree:** `svn st` fails there. stdout is empty, so `isUpdated` is always empty, and the script always takes the "no updates" branch, which prints the **exact validator string** (:75).
- **False success:** UpdateCounterRobotsList is **always Success, and the patch is never created**. The downloaded file is left modified in the worktree until the next `git reset --hard`.
- Conversely, if the update branch ever ran, it prints `committed to svn` (:50) and not the validator string, so it would be marked Failure.

#### gitbot/addGitbotFeature.py (73, read fully)

- **Flow:** appends a JSON record before the last `];` in `~/sourcegit/githubbot/src/plugins/featureConfiguration.ts`, then `git add/commit/push` via `subprocess.run`, return codes unchecked (:46-49).
- `create_new_record` can return None (:41-42), which gives a TypeError at :21.
- **False success:** no validator, so always Success, whether the push failed or it crashed.

#### puppet_workstation_report.sh (32, read fully)

- **Flow:** `curl puppetdb:8080/pdb/query/v4` for Ubuntu inventory (:15), then `jq` → CSV, then mail/s-nail to `<user>@atypon.com`, then `Report generated` (:32). Each step has `|| exit 1`.
- `curl` has no `-f`, so an HTTP error body goes to jq. jq fails and the action fails; that is correct. **No false success found.**

#### updateMjrBranchesList.sh (57, read fully)

- **Flow:** `set -euo pipefail`, then GET the GitHub Actions variable `MJR_BRANCHES_LIST` on `atypon/literatum`, then insert the new branch before `master`, then PATCH, then `Updated MJR_BRANCHES_LIST to: …` (:58). HTTP status is checked on both calls.
- **Gaps:**
  - No dedup: re-running appends the branch twice.
  - An empty `$1` fails under `set -u`.
- Token-like value at :8 (not reproduced).

#### build_opstool.sh (39, read fully)

- **Flow:** `set -e` (:6), then `checkoutGitRepo opstool` (-r), then `ant resolve-dependencies`, then `ant bundle` in `~/sourcegit/opstool`.
  - If `~/apps64/opstool` exists: `mkdir opstool_<ts>`, `cp opstool.zip … && unzip … || echo "Failed to extract…"` (:31), then **`rm -rf ~/apps64/opstool`** (:32) and `mv` the new dir into place (:33).
  - Then `Finished Successfully` (:39).
- **False success:** if the cp or unzip fails, the `|| echo` swallows it. The old opstool is deleted and replaced by an empty or partial dir, and the script still prints `Finished Successfully`.
  - The DS's own test actions (`cd ~/apps64/opstool`, SshExecuteVisitor HostTestJane, NonVisualRegression etc.) then break.
- `return 1/2` at top level (:20, :25, :27) is invalid in an executed script. With `set -e`, the failing ant has already exited the script anyway.

#### webdav_dr_saml_sync.sh (31, read fully)

- **Flow:** `set -e`; for 8 hard-coded clients, `rsync -avz -e "ssh -i ~literatum/.ssh/id_rsa"` of `webdav_directories/samldata/<client>/` to `gcp-rehearsal@gcptools.atypon.com` (:15-30), then `All syncs completed at …` (:32).
- A missing client dir is only a warning, so a run with all dirs missing still succeeds.
- An rsync failure exits (`set -e`), so the action fails correctly.

#### analytics_events/env_hosts_inventory.py (44) + playbook.yaml (14), both read fully

- **Inventory:** every enabled `machine/@name` in `~/deployconf.xml`, plus tools-1..10 and localhost. Bucket `atypon-insights-events-prod` for literatum/readonly, `-nonprod` otherwise.
- **Playbook:** runs `upload_event_logs_to_gcs.py --delete-after-upload` on each host (not read; outside this list).
- **False success:** no validator, so always Success, even with unreachable hosts or upload failures.
- Note: `test=no` means local event logs are **deleted after upload**.

#### operations/cron/pericles_culp_resync.sh (8, read fully)

- **Flow:** `setprod pericles; run tool IAMCacheLoader -Dargs="0 4 350|200|20|<emails> 0 true"` (:8-9).
- No validator, so always Success. It is hard-wired to pericles, whatever product the action targets.

#### xmlqaauto/pull_deploy_xmlqaauto_jar.sh (15, read fully)

- **Flow:** if `~/apps64/xmlqaauto/<v>/xmlqaauto_jar/xmlqaauto-<v>.jar` is missing, runs `mvn dependency:get` ×2 and `mvn …:copy` from the nexus ops-tools repo (:8-13).
- Nothing is checked. A failed download leaves an empty dir, and later runs skip it only if the jar exists, so they retry.

#### pyroscopeProfile.sh (52, read fully)

- **Flow:** `set -e`; finds the PID with `ps aux | grep catalina | grep "$PRODUCT" | head -1` (:25). That is a **substring match**, so for example `aip` also matches `aipp`, and it takes the first match. Then `kill -USR1`, sleep 1-5 min, `kill -USR2` if <5, then `PROFILING_TRIGGERED: Success` (:51).
- **Failures:** `kill` failure exits via set -e; missing PID prints `ERROR:`. Both give a correct Failure.
- **False success:** it can profile the **wrong product's JVM** on a shared host.

#### updateYaegerOnLiteratumBranches.sh (128, read fully)

- **Dead loop:** the loop iterates `item` but tests **`$branch`** (never set) (:12-27). No branch matches `master` or `lit-NNNN`, so **nothing is updated**. It only prints `Processing branch: X`.
- **SVN path, even if reached:** it `cd`s to `${TEMP_DIR}/svn/…` with TEMP_DIR unset (:40) and then `rm -rf "${TEMP_DIR}"` (:55), which would be `rm -rf ""`.
- **git path:** `git commit` would fail under `set -e` when nothing changed.
- **DS result:** status **Cancelled** (no parser, see above), so the no-op is not visible as a failure either.

---

### False-success / silent-failure rows

| Script:line | Mechanism | DS action | Effect |
|---|---|---|---|
| catchpointApi.py:76,125 | Both messages contain `pausing` and `unpausing`; product-not-found prints one and exits 0 | AlertExternalEnable/Disable | Pass whenever catchpoint ran, even if the product wasn't found and pingdom did nothing |
| pingdomApi.sh:298-303 | "pausing/unpausing check" echoed before the unchecked `pingdomApi.py` call | AlertExternal*, UpdateStatusPage | Pass although the API call failed; the shared-dir copy runs, not the repo copy |
| actions.xml:793 | validator `pausing` ⊂ `unpausing` | AlertExternalDisable | Unpause output satisfies the Disable check |
| pd_shift.py:356 | `Successfully created 0 override(s)` printed unconditionally | PagerDutyShifts | Pass with zero overrides |
| video_codec.sh:180 | Unconditional success echo | VideoCodec | Pass with all files missing/errored |
| deployserver_stream_bulk_delete.py:101-114,148 | Delete errors abandoned; "Completed" when queue dequeued; daemon threads killed | CfVideosCleanup | Pass with videos not deleted |
| cloudflare-dns.sh:171,187-194 | Main record prints success before wildcard fails | CloudFlareRecordAdd --multisite | Pass without the `*.P-F.cip` record |
| cloudflare-dns.sh:205-207,221 | Missing main record skipped; wildcard delete prints success | CloudFlareRecordRemove | Pass with the main record never found |
| enable_argo_tunnel.sh:21,72,99 | Output redirected to /tmp file; errors ignored; no validator | EnableArgoTunnel | Always Success, DS log empty |
| svn_to_git_sync.sh:162-163; svn_to_git_setup.sh:93-131,136 | `./svn_to_git_sync.sh` relative path, unchecked push, unconditional final echo, no validator | SyncGitWithSvn | Always Success; branch syncs don't run; can push SVN state over git branches |
| cms/handle_cms_jenkins.sh:46-49,55-57,85-88,94-96,124-127,133-136,165-168,174-177 | `curl` without `-f`; HTTP errors exit 0 → `Done successfully` | CreateCmsJenkinsPipelineFromTemplate, CreateCmsReleaseByJenkins | Pass with template not updated or build not triggered |
| cms/handle_cms_cut_branch.sh:78,129,156 | `git pull` unchecked | GitBranchCreate (cms) | Branch cut from stale parent, Success |
| insightsops/UpdateCounterRobotList.sh:68,75 | `svn st` on git worktree → always "no update" → prints validator string | UpdateCounterRobotsList | Always Success; patch never created |
| gitbot/addGitbotFeature.py:46-49 | subprocess return codes ignored; no validator | AddGitbotFeature | Always Success |
| build_opstool.sh:31-33,39 | unzip failure swallowed, then `rm -rf ~/apps64/opstool` and mv | ToolOpstoolInstall | Success with opstool wiped/partial; breaks DS test actions |
| webdav_dr_saml_sync.sh:28,32 | missing dirs are warnings | SyncWebdavSaml | Success with nothing synced |
| env_hosts_inventory.py / playbook.yaml | no validator | AnalyticsSyncEvents | Always Success |
| operations/cron/pericles_culp_resync.sh:8-9 | no validator; hard-wired pericles | IamRedisCacheLoader | Always Success |
| pyroscopeProfile.sh:25 | substring PID match, head -1 | PyroscopeProfile | Success profiling the wrong JVM |
| updateYaegerOnLiteratumBranches.sh:12-27 | `$branch` vs `item`; loop is a no-op | UpdateYaegerVersion | Nothing updated; DS status Cancelled |
| **Always-FAIL (inverse)** generate_widget_report.sh:46 vs :110 | variable-name typo | GatherProductWidgets | Always Failure even when CSV built |
| **Always-FAIL** analyze_widgets_report.py:143 vs actions.xml:360 | `Excel sheet created` vs `Excel Sheet Created` | AnalyzeWidgets | Always Failure after the upload and the folder deletion |
| **Always-FAIL** MissingMergeDetector.py (no `Done successfully`); actions.xml:2744 no cd | string never printed | MissingMerges | Always Failure (Jira tickets may still be filed) |
| **Always-FAIL** AutomateATM.sh:16 | getopts lacks `b` → usage exit 2 | AtmTraining | Always Failure, nothing run |

### Coverage (fork B)

**Read fully (32 files):**
- pingdomApi.sh, catchpointApi.py, pd_shift.py, MissingMergeDetector.py
- video_codec.sh, video_analytics_v1.py, stream_analytics_v2.py, deployserver_stream_bulk_delete.py
- cloudflare-dns.sh, enable_argo_tunnel.sh, enable_argo_tunnel_functions.sh
- svn_to_git_setup.sh, svn_to_git_sync.sh
- cms/handle_cms_cut_branch.sh, cms/handle_cms_jenkins.sh
- AutomateATM.sh, image_optimizer.sh
- analyze_widgets_report.py, generate_widget_report.sh, insightsops/UpdateCounterRobotList.sh
- gitbot/addGitbotFeature.py, puppet_workstation_report.sh, updateMjrBranchesList.sh, build_opstool.sh, webdav_dr_saml_sync.sh
- analytics_events/env_hosts_inventory.py, analytics_events/playbook.yaml
- xmlqaauto/pull_deploy_xmlqaauto_jar.sh, pyroscopeProfile.sh, updateYaegerOnLiteratumBranches.sh, operations/cron/pericles_culp_resync.sh

All reads went through the secret filter; the removed lines are listed at the top.

**Partially read:** catchpoint.py (596, library; only the methods used, auth lines filtered).

**Not read:**
- CF_video_cleanup.py: not referenced by the DS.
- pingdomApi.py: pingdomApi.sh's API client.
- `_video_codec.py`
- AnalyzeWidget.java
- analytics_events/upload_event_logs_to_gcs.py
- atm/1530+, atm/1610+ trainers: unreachable, because AutomateATM exits first.
- processWatcher.sh
- setup_literatum.sh
- external image-optimizer repo

**Not in repo:** the `/atypon/scratch/personal/shared/` copies of pingdomApi.sh and EmailAlertStarter.sh.

### 2.4 Template-level defects in actions.xml itself (found while indexing)

- **SiteConfigBackup / SiteConfigRestore** (actions.xml:2138, :2179) use a bare `if ( $util.getAccount() == "literatum")` where they need `#if (`. Velocity then meets a stray `#else`/`#end`.
  - Expected outcome: either a template parse error, or both the `run tool` and the `run_gradle.sh` lines typed into bash inside an unterminated `if (`.
  - Either way the action is broken. SiteConfigRestore also has no validator, so it is "Success".
  - Not verified against a real log.
- **CreateNewEmployee** loops `setprod` + run_gradle over every product family (actions.xml:648-656). Its validator `BUILD SUCCESSFUL` is satisfied by **any one** family. run_gradle.sh always exits 0 (02 §4.3).
- **DeleteInfraNewEmployee** (actions.xml:676) carries a hard-coded credential argument on the command line (see §5).

---

## 3. False-success / silent-failure table (all actions in this note)

Sorted by relevance to deploy-failure triage: actions that sit in, or next to, deploy/release trees come first. Fork rows are cited as the forks reported them.

| # | Script:line | Mechanism | DS action | Effect |
|---|---|---|---|---|
| 1 | reinitializeConnPool.sh:69-71; prodPID.sh:28-41 | prodPID is Resin-only, so Tomcat hosts get "can't find pid"; `$?` tests `logInfo`; no validator | FullGC, KillJDBCConnections | **Always Success; does nothing on Tomcat (≥2210)** |
| 2 | InvalidateCloudflareCache.py:23-26 | Live `__main__` is a stub that prints the success text and exits | CfInvalidateCache | **Always Success; no purge ever** |
| 3 | deployConfValidation.sh:61, 71-72 | Success text unconditional; `-r` revision ignored | DeployConfValidation | Success for an invalid deployconf (only a Jira P1, mail and chat say otherwise) |
| 4 | cipRemoveDbAndFs.sh:84, 82/89/95 | Validator text printed before the FS step; subshell-exit pattern | CipProductRemoveDbAndFs | Success with the DB not dropped |
| 5 | CipRemoveDeployedDirectory.sh:64, 68 | `$ProductName_` typo means WARs are never removed; success unconditional | CipRemoveDeployedDirectory, RemoveDeployedDirectory | Old `P_F_*.war` survive; a later HostDeploy can pick a stale WAR |
| 6 | CipRemove*.sh:53-58 | Unchecked `cd`, then "not found → nothing to delete" | CipRemove* | Success when the path was never checked |
| 7 | rsyncContent.sh:139-160 | cms and dos each print `Copied Successfully`; either one satisfies the DS; `run tool create.publisher.cip` not validated | CipProductCreateFS | Success with half the content, or no publisher FS |
| 8 | alertManagerSilencer.py:270-274, 304-310 | Matchers are argparse dest names; HTTP 200 = success | *AlertsSilence | Success with a silence that may match no alert (label names unverified) |
| 9 | catchpointApi.py:76,125; pingdomApi.sh:298-303; actions.xml:793 | Both catchpoint messages contain `pausing` and `unpausing`; pingdom prints before an unchecked API call; `pausing` ⊂ `unpausing` | AlertExternalEnable/Disable | **Maintenance mode can "succeed" without pausing anything** (and it is the shared-dir copy of pingdomApi.sh that runs) |
| 10 | build_opstool.sh:31-33 | unzip failure swallowed, then `rm -rf ~/apps64/opstool` | ToolOpstoolInstall | Success; breaks the DS test actions that `cd ~/apps64/opstool` |
| 11 | v-index.sh:57-69 | `run` → run.sh env guard exits 0; a missing DOIs file only warns | VIndex | `Ran successfully` with nothing indexed |
| 12 | escaped_revisions_cron.sh:44-51, 103-104 | Query exit not checked; empty result counts as success; report deleted on success | ReportEscapedRevisions | Success; no evidence left |
| 13 | appendToPermissionFile.sh:26-28 | `echo $(cp …)` always 0 | GrantIndividualPermission | Success while the live DS permission.csv was not updated |
| 14 | httpsSwitcher.sh:32-33 | Errors → Jira comment + `break`; no validator | HttpsSwitcher | Always Success |
| 15 | major_upgrade_post_actions.sh:17-21 | `exit 1` inside `\| while` subshell | SetPatchRelease | sed errors ignored (but see false-failure F1) |
| 16 | do_optimize.sh:113-124 (A) | Success = no Msg/Level/State lines | DbOptimize | Success on connect failure |
| 17 | do_kill.sh:259-273, 342 (A) | Kill + SET OFFLINE output never checked; exit 0 | DbFlexClone (force-kill) | DB left offline silently |
| 18 | BackupPB.sh:86-107, 13-23 (A) | Restore success = absence of 2 strings; multi-product | PB2restore* / PB2backup | "Restore has been successfully done" with nothing restored |
| 19 | submit_reprocess.sh:64-71 (A) | "(0) … Exit" printed without exiting | SubmitReprocess | Success, and the DS cancels CheckReprocess → submitted reprocess unmonitored |
| 20 | check_reprocess.sh:139, 174 (A) | Unconditional `SUCCESS: reprocessing completed`; attach keyed on addComment | CheckReprocess | Merge/index/report errors hidden |
| 21 | digital_object_reprocess.sh:59/61+220, 216-227, 113 (A) | index.sync's `BUILD SUCCESSFUL` reused; empty do.txt → "No dois"; `isDone output` literal | DigitalObjectReprocess | Success when cli-reprocess failed or nothing was listed |
| 22 | passport_content_reprocess.sh:229-237, 215, 188/323 (A) | Unconditional `BUILD SUCCESSFUL` after the poll; `-berr` output | Check/SubmitPassportReprocess | Success without completion |
| 23 | add_remove_Non_web_instance.py:175, 75, 206-209, 289 vs 327/339 (A) | Markers printed before write/commit; push unchecked; parse-before-pull clobbers | AddNonWebInstance, FinalizeReprocess | Success with deployconf unchanged/unpushed; can revert concurrent deployconf commits |
| 24 | reprocess_LIT-516738.py:107 (A) | Success printed per file | CustomReprocessProduct | Partial failure → Success |
| 25 | pd_shift.py:356 (B) | `Successfully created 0 override(s)` | PagerDutyShifts | Success with zero overrides |
| 26 | video_codec.sh:180 (B) | Unconditional | VideoCodec | Success regardless of errors |
| 27 | deployserver_stream_bulk_delete.py:101-114, 148 (B) | Errors abandoned; "Completed" at dequeue; daemon threads killed | CfVideosCleanup | Videos not deleted |
| 28 | cloudflare-dns.sh:171, 187-194, 205-207 (B) | Main-record success printed before the wildcard fails | CloudFlareRecordAdd/Remove | Multisite `*.P-F.cip` missing, Success |
| 29 | enable_argo_tunnel.sh:21, 72, 99 (B) | Output to /tmp; errors ignored; no validator | EnableArgoTunnel | Always Success, empty DS log |
| 30 | svn_to_git_setup.sh:93-131, 136; svn_to_git_sync.sh:162 (B) | Relative `./svn_to_git_sync.sh`; unchecked push; no validator | SyncGitWithSvn | Always Success; can push SVN state over git lit-2410/2210/master |
| 31 | cms/handle_cms_jenkins.sh (curl without -f) (B) | HTTP errors exit 0 | CreateCms* Jenkins | "Done successfully" without a Jenkins change |
| 32 | insightsops/UpdateCounterRobotList.sh:68,75 (B) | `svn st` on git → always "nothing to commit" branch | UpdateCounterRobotsList | Always Success; patch never created |
| 33 | gitbot/addGitbotFeature.py:46-49; analytics_events/*; pericles_culp_resync.sh (B) | No validator | AddGitbotFeature, AnalyticsSyncEvents, IamRedisCacheLoader | Always Success |
| 34 | pyroscopeProfile.sh:25 (B) | Substring PID match | PyroscopeProfile | Profiles the wrong JVM |
| 35 | updateYaegerOnLiteratumBranches.sh:12-27 + no DS parser (B) | Loop tests unset `$branch` | UpdateYaegerVersion | No-op; status always Cancelled |
| 36 | actions.xml:2232 (CleanupLocalOrphanDbs) | Validator string appears in its own command text | CleanupLocalOrphanDbs | Can never fail |

**False failures** (the action is marked Failure although the work was done or was a no-op):

| # | Where | DS action | Why |
|---|---|---|---|
| F1 | major_upgrade_post_actions.sh:27 | SetPatchRelease | `git commit -m` with no add/pathspec after `sed -i`. As written it cannot commit, so it exits 1 (confirm with a real log) |
| F2 | dtsGetter.sh:62-70, 94-96 | DtsGetter with `-d false` | The validator text is printed only on the disable path |
| F3 | autoRestartToggleSwitch.sh:66, 76 | AutoRestart*/Quarantine* | "already enabled/disabled" exits 0 without the success text |
| F4 | build_docker_db_wrapper.sh:165-166 (A) | BuildDockerDatabaseImage -i | Container exists → exit 0 without `DONE SUCCESSFULLY` |
| F5 | passport_content_reprocess.sh:59,103,120,154 (A) | Passport reprocess | Prints `No DOIs`; the DS expects `No dois` |
| F6 | generate_widget_report.sh:46 vs 110 (B) | GatherProductWidgets | Variable typo; always Failure |
| F7 | analyze_widgets_report.py:143 vs actions.xml:360 (B) | AnalyzeWidgets | Case mismatch; always Failure (after deleting its input dir) |
| F8 | MissingMergeDetector.py; actions.xml:2744 (B) | MissingMerges | Never prints `Done successfully`; no `cd`; SVN-only |
| F9 | AutomateATM.sh:16 (B) | AtmTraining | getopts lacks `b`; exits 2 before doing anything |

**Hangs and locks:**
- do_clone.sh copy loop has no timeout (:341-380); the restore times out only with 0 % progress (:484); a stale global lock gives exit 20 (A).
- check_reprocess.sh infinite poll when the count is empty (:78, :94) (A).
- pingdomApi.sh `lockfile -r 0` exits silently on a held lock (:444, :496) (B).

---

## 4. Model gaps: repos or paths the DS calls that we don't have

These are **unlisted repos**. Per the flag-unlisted-repos rule, raise them now:
- **`developer_productivity`** (`~/sourcegit/developer_productivity/*.sh`): every DB backup/restore/flexclone-restore/Cassandra backup-restore/FTP-cleanup action (about 20 actions). CipRemoveDatabase.sh also sources its `schemeConfig.sh`. Not cloned in `$LIT_REPOS`.
- **`deployserver/scripts/*.sh`** (gitMerge, gitBranchCreate, gitRemoveBranch, gitDryMerge, missingMrMerges, tf_vm_ops, tf_cf_zt, tf_argo_tunnel, updateDsConfFile, revokeDsPerm, checkoutMajorBranchByJenkins, handleRootPomReleaseJenkins). The deployserver repo **is** cloned, but those scripts were not read here.
- **Other external code:**
  - `terraform-infra/deploy_dr.sh`, `gcp-environments`
  - `/root/ansible-fc/fc.py`, `/root/lb/do_managelbpools.sh`, `/etc/puppetlabs/puppet/puppetagent.sh`
  - `infra-scripts/sql-audit/SQLscript.sh`, `PropsManagement`
  - `/home/infrauto/bin/do_*employee.sh`
  - `/archive/s/ansible-sftpusers/manage_sftp_users.sh`
  - `~/apps64/ansible/inventory/ansible-actions.py` (build_docker_db_wrapper, UpdateStatusPage)
  - the Windows `C:\IT\database\datacenter\scripts\dbflexclone.ps1` (source of `Congratulations!`)
  - the external `image-optimizer` repo
  - `/atypon/scratch/personal/shared/{pingdomApi.sh,EmailAlertStarter.sh}`, which are **the copies the AlertExternal*/AlertInternal* actions actually run**
- **Missing everywhere:**
  - `styleguide/styleGuideUpdate.sh`, `deployserver/checkSqlPatchStatement.sh`, `packageStyleguide.py` (as in 02)
  - Insights tooling: `ActivateNonprodPipelines.sh`, `cleanup-javaetl.sh`, `alerts_k8s.sh`, `gcr-cleanup.sh`, `user-interests*.sh`, the `3.87.14.135` test box

---

## 5. Secret-bearing locations (for rotation; values not reproduced)

| Location | What |
|---|---|
| actions.xml:676 (DeleteInfraNewEmployee) | Hard-coded credential argument on the command line; it also lands in every action log |
| actions.xml:1410 (CfVideosCleanup) | API key on the command line |
| cipRemoveDbAndFs.sh:79-80 | Hard-coded DB user and credential in sqsh |
| InvalidateCloudflareCache.py:124 | A token-like string in a comment (the filter missed it) |
| do_clone.sh:537 | FTP URL with inline credential (A) |
| do_dbflexclone.sh:316-317 | Hard-coded sqsh `-P` value (A) |
| cms/handle_cms_jenkins.sh:33,46,55,72,85,94,111,124,133,152,165,174 | Jenkins `user:token` in `curl -u` (B) |
| updateMjrBranchesList.sh:8 | Token-like value (B) |

The keyword filter misses `-P <value>` and `-u user:token` forms. Add ` -P +[^ -]` and ` -u [^ ]+:[^ ]+` to it before printing files from this repo.

---

## 6. Coverage statement

**Read fully: 72 files, ≈11.4k lines.**

- **Me: 27 files, 2,904 lines.**
  - reinitializeConnPool.sh, prodPID.sh, rsyncContent.sh, cipRemoveDbAndFs.sh
  - CipRemoveFileSystem.sh, CipRemoveDeployedDirectory.sh, CipRemoveBackstageLogs.sh, CipRemoveDatabase.sh
  - list_users_permission.sh, autoRestartToggleSwitch.sh, InvalidateCloudflareCache.py, alertManagerSilencer.py
  - httpsSwitcher.sh, appendToPermissionFile.sh, backstage.sh, dtsGetter.sh, dtsSetter.sh
  - major_upgrade_post_actions.sh, setup_literatum.sh, v-index.sh, updateSamlData.sh, installSamlData.sh
  - hbs_detector.sh, escaped_revisions_cron.sh, deployConfValidation.sh, checkWebSiteAdminConfig.sh, host_test.py
  - vpenv.sh (111) was read as a diff against vpenv_quiet.sh (read fully in 02); the only difference is printing.
- **Fork A: 13 files, 3,745 lines.**
  - do_clone.sh, do_optimize.sh, do_dbflexclone.sh, do_kill.sh
  - BackupPB.sh, RestorePB.sh, docker/build_docker_db_wrapper.sh
  - reprocess/{submit_reprocess,check_reprocess,digital_object_reprocess,passport_content_reprocess}.sh
  - add_remove_Non_web_instance.py, processing_scripts/reprocess_LIT-516738.py
- **Fork B: 32 files, 4,786 lines.** Listed in its coverage block in §2.3.

"Fully" means every line was printed through the secret filter. Filtered lines were seen only as "[secret-bearing]". In a few scripts the filter also hid harmless lines (usage echoes containing `-p`, "passport", "PASSED"). The forks re-checked theirs by keyword; mine were usage and DB-query lines.

**Partially read:**
- catchpoint.py (596; only the methods used).
- jDumps.sh (only the two marker lines :137, :150).
- DS `SshExecuteVisitor.runTest` (:575-848, skimmed for the host_test.py path and the verdict strings).

**Not read, and why:**
- **Ant/Gradle targets behind `run tool …` / `run_gradle.sh <task>`:** these are Java/Ant targets in `operations/tools/tool.xml` and literatum, not scripts. Their "BUILD SUCCESSFUL" semantics are in 02 §2.7.
- **Helpers:** `jira_funcs`, `list.py`, `lock.py`/`unlock.py`, `pingdomApi.py`, `_video_codec.py`, `AnalyzeWidget.java`, `VIndexOpTool.java`, `ListUsersPermission.java`, `upload_event_logs_to_gcs.py`, `processWatcher.sh`. They are one hop further and none of them decides a DS verdict string.
- **Not in platform-tools:** the external and missing items in §4.
- `CF_video_cleanup.py`: not referenced by the DS. CfVideosCleanup runs `deployserver_stream_bulk_delete.py` (B).

**Not verified on a host.** All findings come from code; none were checked against real action logs. The two items most worth confirming against logs are F1 (SetPatchRelease) and row 8 (alert silence label names).
