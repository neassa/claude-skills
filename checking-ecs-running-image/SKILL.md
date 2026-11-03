---
name: checking-ecs-running-image
description: Use when asked which ECR image/tag/revision an ECS (Fargate or EC2) service is actually running, why a service "is still on the old image" after a push, terraform apply or console deploy, or how to move a service onto a new image tag (force-new-deployment vs new task-definition revision, mutable tags vs digests).
---

# Which image is this ECS service really running?

The task definition says a **tag**. The running task records a **digest**. Only the digest is the truth. A tag like `:latest` or `:dev` can have moved since the task started.

## Read it (CLI, read-only)

Export the profile first. `AWS_PROFILE=x && aws ...` does NOT export it (see `handing-over-commands`).

```bash
export AWS_PROFILE=<profile> && C=<cluster> && S=<service> && R=us-east-1
# 1. Which revision each deployment uses (PRIMARY = current target)
aws ecs describe-services --cluster $C --services $S --region $R \
  --query 'services[0].deployments[].[status,taskDefinition,rolloutState,runningCount]' --output text
# 2. The newest registered revisions + what image the newest one asks for
aws ecs list-task-definitions --family-prefix <family> --sort DESC --max-items 2 --region $R --query taskDefinitionArns --output text
aws ecs describe-task-definition --task-definition <family> --region $R --query 'taskDefinition.containerDefinitions[0].image' --output text
# 3. The digest each running task pulled
aws ecs describe-tasks --cluster $C --region $R \
  --tasks $(aws ecs list-tasks --cluster $C --service-name $S --region $R --query 'taskArns[]' --output text) \
  --query 'tasks[].containers[].[name,imageDigest]' --output text
# 4. What a tag points at now (compare with 3)
aws ecr describe-images --repository-name <repo> --image-ids imageTag=<tag> --region $R \
  --query 'imageDetails[0].[imageDigest,imagePushedAt,join(`,`,imageTags)]' --output text
```

Console: ECS → cluster → service → **Tasks** → task → **Containers**. The "Image digest" field there is the same value as step 3. Then go to ECR → repo, and find the row with that digest. It shows the tags and the push date.

## Why the service didn't pick up the new image

| Symptom | Cause | Fix |
|---|---|---|
| A new image was pushed to the tag, but the running digest is still old | ECS resolves the tag to a digest **once per deployment** ("software version consistency"). Replacement tasks keep the old digest | `update-service --force-new-deployment` |
| After `terraform apply`, the newest revision has the new image but PRIMARY is still the old revision | The service has `lifecycle { ignore_changes = [task_definition] }`, which is common when CI registers digest-pinned revisions. The apply registers the revision but doesn't move the service | `update-service --task-definition <family>:<new-rev> --force-new-deployment` |
| A console redeploy with only "Force new deployment" ticked stays on the old revision | Force-new-deployment keeps the service's current revision | Console: **Update service** → pick the new revision. CLI: as in the row above |
| The listing shows the newest revisions as N and N-2 | Terraform's `-/+` replace deregistered N-1 (INACTIVE). Services already running on it keep it | Nothing to fix, it's harmless |
| Deployment `rolloutState: FAILED`, back on the old revision | The circuit breaker rolled back after failed health checks | Read the app log (missing migration, bad env var), fix it, redeploy |

`--task-definition <family>` with no revision number means the latest ACTIVE revision.

## Moving a service to a mutable tag

1. Point the task definition at the tag (in terraform, the `container_image` var), then plan.
   - **Read every `environment` change in the task-def diff.** An env var whose default differs from the live value is the real risk; the image line is not.
   - Benign noise in the diff: `hostPort` removed, empty `mountPoints`/`systemControls`/`volumesFrom` removed.
2. Apply. Then move the service onto the new revision explicitly (row 2 of the table).
3. For each later push, a force-new-deployment is enough. Only redeploy once the tag has actually moved; in a promote pipeline that's at the end of the upstream stage.
4. Verify that step 3's digest equals step 4's digest.

The trade-off of a mutable tag: the task definition no longer says what's running. Check the digest instead.

Fully automatic follow-the-tag means an EventBridge rule on `aws.ecr` / `ECR Image Action` / `action-type PUSH` / `image-tag <tag>`, targeting a Lambda that calls `update_service(forceNewDeployment=True)`. EventBridge can't call UpdateService directly. A retag with `ecr put-image` should emit PUSH too, but verify that on the first run.

Project specifics (focus-poc POC follows `:dev`): `focus-poc-envs`.
