---
name: focus-prod-terraform-apply
description: Use when Laith asks to "apply" a merged infra PR on focus prod (account 577211136297, stack envs/prod/40-node-app-prod), or to plan/apply anything in that stack - covers the missing terraform.tfvars drift, the required container_image variable, targeted applies, and the verify step.
---

# Applying a merged PR to the focus prod Terraform stack

"Apply PR N" on an infra PR means `terraform apply` in the stack the PR touched. Read the PR first
(`gh pr view N --repo wiley/aida-emdash --json state,files,body`) to see which stack and whether it is merged.
Laith runs every prod command himself; you hand over short blocks and read what he pastes back
(see `handing-over-commands`, [[focus-prod-aws-profile]]).

## Facts (verified 2026-10-20)

- Stack: `custom/infra/terraform/envs/prod/40-node-app-prod`. State: S3 `ast-prod-terraform`, key
  `envs/prod/40-node-app-prod/terraform.tfstate`. Profile: `AWS_PROFILE=577211136297_AdministratorAccess`
  (pasted short-term creds, ~1 h). First check: `aws sts get-caller-identity --query Account --output text` = 577211136297.
- Worktree: `~/Downloads/projects/aida-emdash-prod-main`, kept detached. Update it with
  `git fetch origin main && git checkout --detach origin/main`, then `git log --oneline -1` must show the PR's commit.
- `container_image` is the only variable with no default, and its validation rejects an empty value. The service has
  `ignore_changes = [task_definition]` (CI deploys by digest), so the value does not roll the service; pass the image the
  service runs today so a plan stays honest:
  ```bash
  C=focus-node-prod-focus
  Q='taskDefinition.containerDefinitions[0].image'
  TD=$(aws ecs describe-services --cluster $C --services $C --query 'services[0].taskDefinition' --output text)
  export TF_VAR_container_image=$(aws ecs describe-task-definition --task-definition $TD --query $Q --output text)
  echo "$TF_VAR_container_image"
  ```
  Expect `909176971711.dkr.ecr.us-east-1.amazonaws.com/focus-poc-node-nonprod@sha256:...` (the shared nonprod repo).

## The trap: no terraform.tfvars, so a full plan shows drift that is not yours

`terraform.tfvars` is gitignored and there is none on this laptop (searched every `aida-emdash*` worktree). Prod was
applied with one that sets non-default values, so a plain `terraform plan` on main shows changes nobody asked for.
Seen 2026-10-20 (3 change, 2 destroy):

| Plan item | Cause (inferred, not confirmed) |
|---|---|
| destroy `module.origin_cert[0]` (key + CSR for `*.focus.wiley.com`) | `create_cloudflare_origin_cert` defaults off; prod was applied with it on |
| media bucket CORS origins `focus.wiley.com` -> `*.focus-prod.literatumonline.com` | main's defaults (commit 66e50b10) vs the tfvars origins |
| `rds.force_ssl` apply_method `pending-reboot` -> `immediate` | not traced |

The same plan also failed refreshing `cloudflare_origin_ca_certificate` (400 missing auth: no Cloudflare token in the
shell), so it was not a complete plan. **Never apply a full plan from this stack until the real tfvars is found.**

## What to do instead: targeted plan, check, apply

Take the resource address from the PR diff (or the plan header), then:

```bash
terraform plan -target=<address> -out=<name>.tfplan
```

Gate: the plan says `1 to change, 0 to destroy` and shows only the attribute the PR changes. Then
`terraform apply "<name>.tfplan"`. The "Resource targeting is in effect" and "Applied changes may be incomplete"
warnings are expected. Delete the plan file afterwards. README of the stack already uses `-target` for prod.

Keep lines short in the block you hand over: a 150-character `TD=$(aws ... --query ...)` line wrapped on paste and
killed the first attempt (empty `TF_VAR_container_image`, validation error). Long `--query` strings go in a variable.

## Verify with AWS, not a hostname

Pick the read that proves the attribute changed. For ALB stickiness:
```bash
TG=arn:aws:elasticloadbalancing:us-east-1:577211136297:targetgroup/focus-node-prod-tg/af83a625e5e5fb5c
aws elbv2 describe-target-group-attributes --target-group-arn $TG --query "Attributes[?Key=='stickiness.enabled']" --output text
```
Then a browser check of the user-visible effect (here: `AWSALB`/`AWSALBCORS` cookies gone, login works).

## State log

- 2026-10-20: PR #722 (AIDAFOCUS-666, ALB stickiness off) applied with `-target=module.ecs_app.aws_lb_target_group.this`;
  `stickiness.enabled` read back `false`. Browser cookie check not yet reported. The three drift items above remain open.
- Open: find or recreate prod's `terraform.tfvars` (ask Laith/SRE where it lives), then re-plan without `-target`; the
  destroy of `module.origin_cert[0]` must not run unless intended.
