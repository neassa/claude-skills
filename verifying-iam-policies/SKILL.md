---
name: verifying-iam-policies
description: Use when designing, requesting, or testing an AWS IAM policy or SSO permission set — "what inline policy do we need for X", least-privilege access for a team or role, or proving a granted policy actually allows and denies the right things. Covers reading the real policies behind SSO permission sets, simulate-custom-policy gotchas, safe live probing, and the actions whose deny you CANNOT prove by probing.
---

# Verifying IAM policies and permission sets

Two jobs: work out what a policy must contain, and prove it does what you claimed. Never hand a policy to an admin, or declare one working, on reasoning alone — both halves are testable.

## Read what the existing roles actually have

**Do not describe a permission set from memory or from a simulate sweep.** Simulate tells you the effective answer for the actions you thought to test; the documents tell you the shape.

IAM Identity Center usually lives in the *management* account, so `sso-admin list-permission-sets` fails from a member account. The provisioned roles are right there in the member account and carry the same documents:

```bash
aws iam list-roles --path-prefix /aws-reserved/sso.amazonaws.com/ --query 'Roles[].RoleName' --output text
aws iam list-attached-role-policies --role-name AWSReservedSSO_<set>_<hash>
aws iam get-role-policy --role-name AWSReservedSSO_<set>_<hash> --policy-name AwsSSOInlinePolicy
aws iam get-role --role-name AWSReservedSSO_<set>_<hash> --query 'Role.MaxSessionDuration'   # session length
```

Burned 2026-09-20: a memory recorded two permission sets as "identical on everything tested". Their *managed* policies were identical; their *inline* policies were wildly different, and only one was the terraform-capable role. The simulate sweep that produced "identical" had never touched the actions where they diverged.

## Build the policy

- **Start from an AWS managed read policy plus a small inline delta**, not a hand-rolled service list. Grants in a base set are partial in unpredictable ways.
- **Check what the managed policy actually contains** rather than assuming. `ReadOnlyAccess` (verified 2026-09-20) has `secretsmanager:Describe*/List*` but **no `GetSecretValue`**, `ssm:Describe*/Get*/List*` but **no `StartSession`**, `kms:Describe*/Get*/List*` but **no `Decrypt`**:
  ```bash
  V=$(aws iam get-policy --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess --query 'Policy.DefaultVersionId' --output text)
  aws iam get-policy-version --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess --version-id "$V" \
    --query 'PolicyVersion.Document' --output json | grep -oE '"(secretsmanager|ssm|kms):[A-Za-z*]+"' | sort -u
  ```
- **Name resources by a suffix pattern when the naming carries the privilege.** `dbuser:<resource-id>/*_ro` matches exactly the read-only DB roles, can never match an app/migrator/admin user, and picks up future environments for free. Pin the instance/resource id too unless you want any future instance included.
- **Add an explicit Deny for the indirect routes to the thing you just restricted.** A read-only DB grant is worthless if the principal can read the secret holding a writable password, decrypt the terraform state, or exec into a container sitting next to the database. Explicit Deny survives someone attaching a broader managed policy later.
- **Verify a Deny is free before adding it.** Denying `kms:Decrypt` breaks S3 reads if buckets are SSE-KMS and log reads if log groups are encrypted. Check first: `aws s3api get-bucket-encryption`, `aws logs describe-log-groups --query 'logGroups[].kmsKeyId'`.
- **Two statements, not one, for `ssm:StartSession`**: the instance (optionally with a tag condition) and the allowed documents. Merging them makes any condition apply to the document resource too, and the document check then fails.

## Simulate before it exists

`simulate-custom-policy` tests a policy document with nothing created. Two syntax traps cost real time:

```bash
POL="$(cat policy.json)"     # NOT file:// — that is parsed as a LIST parameter
                             # and fails "Policy input list item 1 has invalid content"
aws iam simulate-custom-policy --policy-input-list "$POL" \
  --action-names rds-db:connect --resource-arns "$ARN" \
  --query 'EvaluationResults[0].EvalDecision' --output text
```

Condition keys need a JSON file; the `Key=Value` shorthand is rejected:
```bash
cat > ctx.json <<'EOF'
[{"ContextKeyName":"ssm:resourceTag/Project","ContextKeyValues":["my-proj"],"ContextKeyType":"string"}]
EOF
aws iam simulate-custom-policy ... --context-entries file://ctx.json
```

Simulate the **negative** cases with the same care as the positive ones: the privileged user that must be denied, the resource in another project, the shell document. `allowed` on the three you wanted proves nothing on its own.

Use `simulate-principal-policy` against the provisioned SSO role ARN once the set exists — it is the only way to tell an explicit Deny from an implicit one.

## Probe live, without executing anything

Once granted, test as the real profile. Aim mutating actions at **deliberately bogus targets** so an unexpected *allow* still cannot do damage — the error tells you which it was:

| Probe | Denied looks like | Allowed looks like |
|---|---|---|
| `ssm send-command --instance-ids i-00000000000000000` | `AccessDeniedException` | `InvalidInstanceId` |
| `ecs execute-command --cluster nope --task nope` | `AccessDeniedException` | `ClusterNotFound` |
| `rds delete-db-instance --db-instance-identifier nope` | `AccessDenied` | `DBInstanceNotFound` |

### The actions you cannot probe this way

**`kms:Decrypt` with a garbage ciphertext proves nothing.** KMS parses the blob to find the key *before* the key-scoped authorization check, so random bytes return `InvalidCiphertextException` whether or not the action is denied. Probe `kms:DescribeKey` instead — a denial there reports "no identity-based policy allows", which establishes the principal holds no KMS permissions at all. Same shape for any API that validates input before authorizing.

**`rds-db:connect` simulates as implicitDeny but works live.** Trust live tests over simulate in both directions.

## Prove the other half in the resource

An IAM grant is only one layer. For a database, IAM decides *who may connect as which user*; the engine decides what that user may do. Test both, and expect different wording than you assume:

```sql
-- as the read-only role
INSERT ... ;  -- permission denied for table <t>
CREATE TABLE; -- permission denied for schema public
DROP TABLE;   -- must be owner of table <t>     <-- NOT "permission denied"
```
Grepping only for `permission denied` reports DROP as passing. Check the object still exists afterwards rather than trusting the message.

## Report honestly

State which half you verified. "Simulated" and "ran live" are different claims, and "explicit Deny" versus "no Allow anywhere" is a distinction you often cannot make without an admin profile. Say so instead of implying the stronger one.
