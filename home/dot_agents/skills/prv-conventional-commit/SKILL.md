---
name: prv-conventional-commit
description: 'Draft, review, and repair Conventional Commit messages from a git diff, staged changes, or a change description. Use for conventional commits, commit messages, squash titles, type or scope selection, breaking-change footers, and message validation. Uses the official Conventional Commits 1.0.0 specification by default. Only when active commitlint configuration or hooks are detected, also loads and applies the upstream committing-with-commitlint skill and enforced rules. Never stages or commits unless explicitly requested.'
argument-hint: 'Provide a diff, changed files, proposed message, or ask to inspect the current repository; optionally request message-only, review, split, or commit execution.'
---

# Conventional Commit

Create a commit message that is structurally valid, faithful to the change, and compatible with the repository that will consume it. Treat the diff as evidence and Conventional Commits 1.0.0 as the baseline specification. Commitlint is an optional repository-specific overlay, never an assumed dependency.

Read [`references/conventional-commits.md`](./references/conventional-commits.md) before drafting or reviewing a message. It distinguishes specification requirements from common style preferences and contains the type, scope, breaking-change, trailer, and validation rules.

## When to Use

- Draft a Conventional Commit from staged changes, a diff, changed files, or a plain-language description.
- Review or repair a proposed commit message or squash-merge title.
- Choose a type or scope without reducing a mixed change to a vague `chore`.
- Detect whether a change needs `!` or a `BREAKING CHANGE:` footer.
- Explain a commitlint failure when active commitlint usage is evidenced.
- Split unrelated changes into coherent commit-message candidates.

This skill decides and validates the message. If another workflow handles staging or commit execution, settle the message here first. Do not silently stage files, create a commit, amend history, or invoke another workflow, except for the conditional upstream commitlint skill required by step 2.

## Inputs and Modes

Work from any of these inputs:

- the current repository and its staged or unstaged changes
- a pasted diff or patch
- a list of files plus an explanation of the change
- an existing commit message to review
- a pull request diff when the requested output is a squash title or message

Infer the mode from the request:

| Mode | Result |
| --- | --- |
| Draft | One message for one coherent change; this is the default |
| Review | A verdict, precise findings, and a repaired message when needed |
| Split | Separate messages with the change group each message covers |
| Message only | The commit message with no rationale or command |
| Execute | Create the commit only when the user explicitly asks for execution |

If there is no repository evidence, diff, change description, or message to review, ask for the missing input. Do not invent a change.

## Evidence Order

Use evidence in this order:

1. The exact change set the message will describe.
2. Explicit user-provided intent and factual context.
3. Enforced commitlint configuration, only when step 2 detects active commitlint usage.
4. Other explicit repository instructions and enforced configuration.
5. Consistent patterns in recent relevant commit history.
6. Conventional Commits 1.0.0 and the defaults in the reference.

The diff determines what changed. User context may establish why it changed. Commit history reveals local form, but repeated history does not override an enforced rule or justify an inaccurate message.

## Procedure

### 1. Establish the change set

Use user-provided content directly when it identifies the intended change. When inspecting a repository:

1. Read repository instructions that govern commits.
2. Inspect concise status before reading content.
3. If tracked changes are staged, analyze the staged diff and staged file list only.
4. If nothing is staged, analyze tracked working-tree changes only.
5. List untracked files, but read or include them only when the user identifies them as part of the change and they are safe to inspect.

Never silently combine staged and unstaged changes. State which snapshot was analyzed when the distinction matters. For a squash message, compare the pull request or branch with its merge base rather than using unrelated working-tree changes.

If reviewing a message without its diff, validate syntax and wording, but mark semantic fit, atomicity, and breaking-change coverage as unverified.

### 2. Detect commitlint and select the rule path

Do not assume commitlint from Conventional Commit-style history, a documentation mention, or an installed dependency alone. Treat commitlint as active only when at least one of these is present in the target repository or supplied as evidence by the user:

- `.commitlintrc` or `.commitlintrc.{json,yaml,yml,js,cjs,mjs,ts,cts,mts}` at the repository or workspace root
- `commitlint.config.{js,cjs,mjs,ts,cts,mts}` at the repository or workspace root
- a top-level `commitlint` field in `package.json`
- a commit-message hook that invokes commitlint, such as `.husky/commit-msg`, `lefthook.yml`, `lefthook.yaml`, or `.git/hooks/commit-msg`
- actual commitlint configuration, hook output, or rejection output supplied for the target repository

Choose exactly one branch:

**When commitlint is active:**

1. Fetch and read the upstream [`committing-with-commitlint` skill](https://raw.githubusercontent.com/conventional-changelog/commitlint/master/skills/committing-with-commitlint/SKILL.md) in full before writing or validating the message.
2. Apply that skill together with this one. This skill governs semantic truth, atomicity, scope usefulness, and breaking-change analysis; the upstream skill and resolved repository configuration govern enforced message form.
3. Follow the upstream workflow to inspect the effective rules, validate the complete message, and self-correct named violations. Resolve the repository's existing commitlint executable without installing packages. If it is unavailable, report that commitlint is configured but cannot be run.
4. If the upstream skill cannot be loaded or the commitlint configuration cannot be resolved, do not substitute common preset defaults or claim commitlint compliance. State the limitation and provide only a clearly labeled provisional message when useful.

**When commitlint is not active:**

1. Do not fetch or apply the upstream commitlint skill.
2. Do not run commitlint, install it, initialize a configuration, or infer rules from `@commitlint/config-conventional`.
3. Use this skill and the official Conventional Commits 1.0.0 reference as the complete standard workflow. Explicit non-commitlint repository instructions may still add local style, but label them as local policy rather than commitlint requirements.

### 3. Discover remaining repository policy

Look narrowly for policy that can change the result:

- contribution or repository instructions
- release or changelog configuration that interprets commit types
- recent non-merge subjects, especially in the affected package or component

Use recent history to learn stable scope names and house style, not to copy an old message. If no local policy exists, use the reference defaults. If local policy conflicts with strict Conventional Commits syntax, explain the conflict instead of claiming both are satisfied. Handle commitlint only through step 2; do not treat it as a generic convention.

### 4. Test atomicity

Summarize the change's single purpose in one sentence before choosing a type. Supporting tests, documentation, generated output, and lockfile updates normally belong to the behavior they support and do not need separate types.

Recommend a split when changes have independent purposes, could be reverted separately, or require different release signals. In Split mode, map each proposed message to concrete files or hunks. Do not hide unrelated work behind `chore`, a broad scope, or a long body.

### 5. Choose the type

Choose the type from the change's purpose and externally observable effect, not from the most numerous file extension:

- `feat` adds a capability for a user or consumer.
- `fix` corrects defective behavior.
- `perf` improves measured or clearly evidenced performance without changing the intended capability.
- `refactor` changes internal structure without changing intended behavior.
- `docs`, `test`, and `style` apply when those are the change itself, not merely support for a feature or fix.
- `build` changes the build system or dependency machinery; `ci` changes automation.
- `chore` is a narrow maintenance fallback, not a label for uncertainty.
- `revert` identifies an intentional reversal and should name the reverted change when known.

Only `feat` and `fix` have meanings required by the base specification. Treat every other allowed type as repository policy or a documented default. Prefer a repository's established custom type when its tooling permits it.

### 6. Choose the scope

Use a scope only when it adds stable, useful context. Prefer the repository's existing package, service, feature, command, or subsystem name. In a monorepo, inspect the affected package's history before inventing a scope.

Omit the scope for a genuinely repository-wide change or when no stable name is supported by evidence. Do not join unrelated scopes with commas or slashes; split the change when those areas represent independent purposes.

### 7. Detect breaking changes

Check changed public APIs, commands and flags, configuration and environment variables, schemas and persisted data, events and wire formats, extension points, supported runtimes, and documented consumer behavior. A private rename or internal refactor is not breaking by itself.

When a breaking effect is clear, place `!` immediately before the colon. Add a `BREAKING CHANGE: <description>` footer when the impact or migration cannot be understood from the subject alone; using both is valid. Follow stricter local policy when present.

If the evidence only suggests a possible break, ask one focused question or state the uncertainty. Never manufacture migration advice.

### 8. Compose the message

Build the header as:

```text
<type>[optional scope][optional !]: <description>
```

Unless the repository says otherwise, use a lowercase type, an imperative present-tense description, no trailing period, and a concise header of at most 72 characters. These are quality defaults, not requirements of Conventional Commits 1.0.0.

Add a body only when it contributes verified context: the reason for the change, the previous failure mode, an important design choice, or user impact. Do not narrate the file list or restate the subject. Keep factual claims traceable to the diff or user context.

Add footers as valid trailers. Preserve exact issue references, acknowledgements, and co-author lines supplied by the user or repository evidence. Never invent an issue number, incident, metric, reviewer, or breaking-change impact.

### 9. Validate before returning

Run the reference checklist in this order:

1. specification syntax
2. repository-policy compliance
3. type and scope accuracy
4. subject clarity
5. body and trailer structure
6. breaking-change coverage
7. atomicity and factual support

In Review mode, keep these verdicts separate. A message can be valid under Conventional Commits but fail commitlint, or pass syntax while misrepresenting the diff.

When step 2 detects commitlint, also perform the upstream skill's full-message validation against the resolved configuration before returning. Report commitlint compliance only when that validation actually runs. When commitlint is absent, omit commitlint status entirely.

### 10. Present the result

For Draft mode, return the exact message in one copyable text block. Follow it with at most three short bullets explaining the type, scope, and breaking-change decision. Omit those bullets in Message-only mode.

For Review mode, use:

```text
Verdict: valid | valid with repository-policy warnings | invalid | cannot fully verify
Findings: <only concrete issues, in priority order>
Suggested message: <include only when a repair is useful>
```

For Split mode, identify the files or hunks for each logical commit, then provide an ordered message for each. Do not stage the groups unless explicitly asked.

When one missing fact blocks an accurate result, ask one focused question. A clearly labeled provisional message may accompany the question when it still helps.

### 11. Execute only on explicit request

Before creating a commit, re-check status and confirm that the staged diff is the same snapshot used to compose the message. Commit only staged changes unless the user explicitly authorizes staging a named set. Preserve multiline bodies and footers without flattening them into the subject.

Do not amend, bypass hooks, alter Git configuration, force-push, or stage unrelated files unless the user separately and explicitly asks. If a hook rejects the message, report the exact failure, repair the message when possible, and retry only with the user's original execution request still in scope.

## Guardrails

- Never claim a motivation, regression, performance gain, compatibility break, or release effect that the evidence does not support.
- Never call a style preference a requirement of the Conventional Commits specification.
- Never choose `feat` for internal developer work unless it adds a capability to the repository's actual consumers.
- Never choose `fix` merely because a test changed; identify the defective behavior being corrected.
- Never mark a change as breaking solely because it is large.
- Never force one message onto independent changes for the sake of convenience.
- Never load, run, install, or emulate commitlint when step 2 finds no active usage.
- Never claim commitlint compliance when the upstream skill, effective configuration, or existing executable could not be used.
- Never expose secrets encountered in status, diffs, configuration, or history.
