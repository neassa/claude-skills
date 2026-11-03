---
name: writing-comments
description: Use when drafting anything published in the user's name — PR descriptions, GitHub/Jira ticket comments, commit messages, review replies, or status updates shared with the team. Also when the user asks for "a quick comment", "2 lines", or to fix/lean a description.
---

# Writing comments in the user's style

Terse, factual, plain. Every sentence carries information; nothing performs. Written for a teammate who wants the state of things and what's needed — not a narrative.

## Use his words (settled 2026-09-02)

When Laith gives his own phrasing — a description he typed, a "phrase this: …", a rough draft — **keep his words and structure.** Fix grammar/spelling and tighten only; do not re-voice into polished corporate prose. He said plainly: "no need for too much junk words, simple is better sometimes." A rougher sentence in his voice beats a smoother one in yours.

- Preserve his framing and any headings he used ("what we have", "the idea", "the gates").
- Cut filler, don't add it: no "comprehensive/robust/seamless/leverage/in order to". Prefer the shortest true sentence.
- Explain by plain effect, not by mechanism, unless he asked for the mechanism.
- When in doubt, under-write. He can always ask for more; he rejects padding.

## Hard rules

- **No emoji, no greetings, no thanks, no sign-offs, no hedging.** No AI disclosure, no Claude footer, no PR template/checklists — description only (established for aida-emdash PRs; default everywhere).
- **Lead with the current state**, then the ask or fix: "X now works except one gap: Y" → "please add Z".
- **Default length: 2 lines for a ticket comment** unless asked for more. One sentence of status, one sentence of ask/next step.
  **Two SHORT lines, about 20 words each** (2026-10-12: a 2-line import summary with every count and check in it got "short"; the accepted version kept only the headline numbers: "Full import loaded on Dev (912 entries), and all 152 Key Opinions loaded on UAT and checked; nothing missing."). Detail stays in chat.
- **Backtick every identifier**: IAM actions, env vars, flags, table names, branch names. Reference PRs/tickets inline as `#332`, `AIDAFOCUS-253`.
- **No dates in his comments** — not in notes, sheet cells, docs, PR/ticket text or code comments he will share. He said it plainly: "do not add dates to my comments". No "(decision 2026-09-29)", "reported 2026-09-23", "the 17 Sep email", "Generated 29 September 2026", "(Laith 2026-09-28)". Say what was decided and by whom only if it matters ("not imported by decision"), never when. Dates that are DATA stay (an article's published date, an export folder named `2026-09-01`, a placeholder `2020-01-01`). If timing genuinely matters to the reader, ask first. Never "yesterday/last week" either.
- **Numbers inline**, not behind links: durations, counts, req/sec, HTTP codes. Commands shown copy-pasteable with secrets/keys redacted.
- **One clause of why, not a paragraph**: "…lost when the new inline policy replaced the old one" is enough history.
- **Scope discipline**: a comment/PR does exactly what it says. A revert PR contains the revert — no drive-by warnings, docs, or "while I'm here" extras.

## PR descriptions

**Default shape (Laith's own rewrite of `#555`/`#556`, 2026-09-28 — "write like this"):**

1. **Summary sentence first.** "This pull request makes a small but important change to X. <What changed> to <prevent/fix what>." Two sentences at most.
2. **A bullet per change.** Each bullet names the thing, old → new value, where, and why in one clause: "Updated the `instance_type` for the `ssm_jump` module from the default (previously `t4g.nano`) to `t4g.small` in `main.tf` to avoid memory exhaustion when running dnf patching alongside the SSM agent."
3. **Problem paragraph.** What the resource is, what happened, the concrete evidence (counts, sizes, error strings, status values), why the obvious workaround did not help. No timestamps or "on <date> at <time>" — he deleted that.
4. **`Fix:` line.** The exact change, with the file path, plus what stays as it is.

**Leave out of the description:** operational notes (what a plan should show, what applying does, rollout order), follow-ups and "separate issue" paragraphs, verification narratives. He deleted all of these from `#555`. Say them in chat instead.

Worked example (as merged into `#555`/`#556`):

> This pull request makes a small but important change to the `ssm_jump` module configuration. The EC2 instance type has been updated to `t4g.small` to prevent out-of-memory issues during patching.
>
> - Updated the `instance_type` for the `ssm_jump` module from the default (previously `t4g.nano`) to `t4g.small` in `main.tf` to avoid memory exhaustion when running dnf patching alongside the SSM agent.
>
> The nonprod SSM jump host (`i-0b2671c177b8083dd`, `module.ssm_jump`) is a `t4g.nano` with 0.5 GB. The Quick Setup patch run (`AWS-RunPatchBaselineAssociation`) started `dnf` on it, and the box ran out of memory: the console log shows the OOM killer firing, `dnf` holding ~140 MB in RAM plus ~330 MB in swap, and the SSM agent swapped out. From then on every port-forward session hung at "Starting session" and Run Command came back `Undeliverable`, while the agent still showed `Online`. CPU sat at 80-96% and two reboots did not help, because the patch run starts again after boot.
>
> Fix: pass `instance_type = "t4g.small"` (2 GB) to `module.ssm_jump` in `envs/nonprod/10-foundation/main.tf`. The module default stays `t4g.nano`.

Older shapes, superseded by the one above unless he asks for them: the prose-only problem → fix → verification → ops-notes layout; the `#397` (2026-09-06) hybrid, whose bullet inventory lives on as step 2; and the `#374` (2026-09-01) bug-fix "In one sentence: … + numbered failure chain" plain-language version — use that only when he asks for "the simple version".

## Ticket comments — the canonical shape

> Terraform plan/apply on the node stack now works except one read-only gap: the OIDC provider data-source needs `iam:ListOpenIDConnectProviders`, currently denied for both SSO roles.
> Also please re-add `iam:SimulatePrincipalPolicy` (verified still denied as of Aug 20) — it was granted Aug 14 but lost when the new inline policy replaced the old one; policy JSON attached.

## Sprint-report / leadership bullets (calibrated 2026-09-01, FOCUS sprint report)

A different genre from ticket comments: team voice ("we"), short plain sentences a non-technical reader follows in one pass. NOT the terse dash-compressed register above — Laith rejected "stable and demo-ready — configuration done on both sides, testing cases passed…" and asked for "more simpler and in my words".

- **Scope by PROJECT, not by who did the work.** Only items belonging to the project being reported (LIT incident cleanup is separate Atypon ops work — never in a FOCUS sprint report; corrected 2026-09-01).
- **Plain effects instead of jargon:** "logins survive deploys and we can run more than one container", "no shared passwords" — not "stickiness", "IAM auth", "session driver".
- **Comparative claims only if self-explaining.** "~2x faster than the current hosted one" got "what do you mean?" — spell out what's compared to what, or drop the claim.
- **Don't trade accomplishments for brevity.** He'd rather list every real item in simple words (config work on both CF and AWS, testing cases, the session fix, automation scripts, access work, test data) than have a short vague line — he added items back three times.

Approved shape: one bullet, 3–5 plain sentences, each naming a concrete thing done and its everyday effect.

## Review findings for content/product (calibrated 2026-09-21, FOCUS migration samples)

A findings list for Samara/Jen/Elena, not for engineers. **One bullet = the observation + an example link. Nothing else.**
Laith rewrote a draft of mine and cut, from every bullet: the mechanism, the counts, the test numbers, and the
"Decide: a, b or c" ask. What survived was what a reader can see on the page.

- **Name the thing, then what the reader sees.** "Hero/card image cropping. The hero slot is a fixed frame, and causing the image to gets cut." — not `16:9`, not `object-fit: cover`.
- **Compare 1.0 with 2.0 in plain words**, and link both pages when they differ: "The word showed in Focus 1.0 and it is not showing in 2., should it be shown?"
- **A plain question is the ask.** "should it be shown?" — never an options list, a recommendation, or a table of trade-offs.
- **No numbers, no XML element names, no CSS.** "it is not in the XML file, so it does not migrate" — he says "XML file", not "deposit". My "42 clicks, 8 landed, three site changes would fix it" became "the results were faulty".
- **Keep one concrete example link per bullet**; drop the corpus-wide counts even when they are right. Those belong in a reply if someone asks.

Keep the numbers and the mechanism for the engineering ticket (`AIDAFOCUS-366`) or for chat with Mayank/Alok — the same finding gets two registers.

## Bench/test results (chat or comment)

Report the command (key redacted) + duration (min) + req/sec (or the equivalent core numbers) inline — never only a link or artifact.

## Anti-patterns (each rejected by the user at least once)

| Draft says | Should say |
|---|---|
| Long context-setting paragraph before the point | The point, first sentence |
| Filler: "comprehensive", "robust", "seamless", "leverage" | "This pull request makes a small change to X to prevent Y" |
| Checklist/template sections, AI-generated disclosure | Plain description only |
| Bundled extra change "for safety" | Only what was asked; propose extras separately |
| "recently/currently" ambiguity | PR / ticket numbers, no dates |
| "(decision 2026-09-29)", "reported 2026-09-23" in a note or comment | "(decision)", or nothing |
| Options list or "Decide: a, b, c" in a findings bullet | A plain question, or nothing |
| Counts and test numbers in a content-team bullet | The observation plus one example link |
