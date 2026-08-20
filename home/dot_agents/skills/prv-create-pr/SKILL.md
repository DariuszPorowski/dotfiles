---
name: prv-create-pr
description: "Create a GitHub pull request from a clean, fully synchronized branch. Use when opening, publishing, or submitting the current branch as a PR, including fork-based workflows and draft PRs. Resolves base and head repositories, prevents duplicate creation, honors PR templates, and uses prv-conventional-commit to draft or validate the PR title from the exact branch diff."
argument-hint: "Optionally provide the base branch, draft status, proposed title, or additional PR context."
---

# Create GitHub Pull Request

Create a pull request from the current branch without changing its content or history. Fetching remote refs is allowed. Never commit, push, rebase, merge, stash, switch branches, or discard changes as part of this workflow.

## Inputs

- An explicit base branch overrides the base repository's default branch.
- A user-provided title is a candidate to validate, not a reason to bypass `prv-conventional-commit`.
- Create a non-draft PR unless the user requests a draft or clearly describes the work as unfinished.
- Use additional user context only when it is factual and consistent with the diff.

## Procedure

### 1. Resolve Repositories and Refs

1. Verify that the current directory is in a Git worktree with `git rev-parse --show-toplevel`.
2. Read the current branch with `git branch --show-current`. Stop if it is empty because detached `HEAD` cannot identify a PR head branch safely.
3. Resolve the configured upstream with `git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}"`. Stop if it is missing.
4. Resolve the head remote and remote branch from the current branch's Git configuration. Do not assume that the local and remote branch names match. Stop if the remote is local-only (`.`) or no longer exists.
5. Select the base remote from the exact names returned by `git remote`: use `upstream` when present; otherwise use `origin`. Stop if neither exists.
6. Resolve the base repository's default branch from `refs/remotes/<base-remote>/HEAD`. If that symbolic ref is unavailable, use `git remote show <base-remote>` and its `HEAD branch`. Stop rather than guessing if neither method succeeds. Retain its remote-tracking ref as `baseDefaultRef` for template discovery.
7. Set the base branch to the user's explicit choice when supplied; otherwise use the resolved default branch.
8. Fetch the head and base remotes with `git fetch --no-tags <remote>`, fetching once if they are the same. Stop if either fetch fails; stale refs are not sufficient evidence for PR content.
9. Verify that `refs/remotes/<head-remote>/<head-branch>`, `refs/remotes/<base-remote>/<base-branch>`, and `baseDefaultRef` exist after fetching.
10. Resolve the base and head GitHub repository identities through the GitHub tool or `gh repo view <remote-url> --json nameWithOwner`. Do not infer owners by manually splitting remote URLs.

Keep these values for later steps: `headRemote`, `headBranch`, `headOwner`, `baseRemote`, `baseDefaultRef`, `baseBranch`, `baseOwner`, `baseRepo`, and `baseRef`.

### 2. Validate Branch State

1. Require empty output from `git status --porcelain=v1 --untracked-files=all`.
2. Run `git rev-list --left-right --count "@{upstream}...HEAD"` after fetching:
   - A nonzero left count means the remote branch contains commits missing locally.
   - A nonzero right count means local commits have not been pushed.
   - Stop for either condition so the analyzed `HEAD` exactly matches the remote PR head.
3. Require a merge base between `baseRef` and `HEAD` using `git merge-base <base-ref> HEAD`.
4. Confirm that `git diff --quiet <base-ref>...HEAD --` reports changes. Exit code `0` means there is nothing to submit, `1` means changes exist, and any other code is an error.
5. Stop if the base and head repository identities and branch names are identical.
6. Search the base repository for an open PR with the exact head owner, head branch, and base branch. If one exists, report its URL and stop successfully instead of creating a duplicate.

### 3. Capture the PR Snapshot

Record `validatedHead` with `git rev-parse HEAD`. Analyze only the merge-base change set represented by `<base-ref>...<validated-head>`:

- Read the full diff, diff stat, changed paths, and commits unique to the branch.
- Treat the diff as evidence of what changed and user context as evidence of why.
- Do not include secrets, credentials, tokens, or unrelated local configuration in generated content or reports.
- Do not use unrelated working-tree changes or commits outside this range.

### 4. Load the PR Template

Read templates from the base repository's default-branch ref, not from the working tree. Check these single-template paths in order:

1. `.github/PULL_REQUEST_TEMPLATE.md`
2. `.github/pull_request_template.md`
3. `docs/PULL_REQUEST_TEMPLATE.md`
4. `PULL_REQUEST_TEMPLATE.md`

If none exists, look for Markdown files under these directories:

- `.github/PULL_REQUEST_TEMPLATE/`
- `docs/PULL_REQUEST_TEMPLATE/`
- `PULL_REQUEST_TEMPLATE/`

Use the only matching template. If several templates exist and the user did not identify one, ask one focused question rather than choosing arbitrarily.

### 5. Generate and Validate the PR Title

1. Load and follow the `prv-conventional-commit` skill. Stop if it is unavailable. Do not reproduce or override its type, scope, breaking-change, atomicity, or validation rules here.
2. Ask it for a squash title using the exact PR diff as the change set and branch commits as supporting context:
   - Use **Message only** mode when drafting a title.
   - When the user supplied a title, validate and repair it first, then request the final result in **Message only** mode.
3. If the skill determines that the branch contains unrelated changes requiring separate messages, stop and report the proposed split instead of forcing a vague title.
4. Accept only one nonblank line no longer than 80 characters. If the result includes a code fence, body, rationale, or extra lines, ask the same skill to repair its output.
5. Use the validated header verbatim, including its type, optional scope, and optional `!`. Do not create a commit.

### 6. Generate the PR Description

When a template exists:

- Preserve its heading order, HTML comments, and checkboxes.
- Replace placeholders only with facts supported by the diff or user context.
- Never mark an unverified checklist item as complete.
- Never invent issue numbers, test results, performance claims, reviewers, or rollout details.

When no template exists, include concise `Summary` and `Validation` sections. Explain the purpose and reviewer-relevant behavior rather than narrating every file. Include validation commands and results only when they were actually run; otherwise state that validation was not run.

### 7. Revalidate and Create

Immediately before the write operation:

1. Confirm that the worktree is still clean.
2. Confirm that `git rev-parse HEAD` and `git rev-parse "@{upstream}"` both equal `validatedHead`.
3. If any value changed, restart validation and regenerate content from the new snapshot.

Prefer `github-pull-request_create_pull_request` with these values:

- `repo`: the owner and name resolved from the base remote
- `head`: the remote head branch name, without an owner prefix
- `headOwner`: the head repository owner when it differs from the base owner
- `base`: the resolved base branch
- `title`: the verbatim title from `prv-conventional-commit`
- `body`: the generated description
- `draft`: the resolved draft status

Use `gh pr create` only when the GitHub creation tool is unavailable. Pass the body through a temporary file rather than interpolating multiline Markdown into a shell command, and delete the temporary file afterward.

Do not blindly fall back or retry after a creation error. If the outcome is uncertain, search again for the exact head/base PR first. Retry only when no PR exists and the failure is clearly transient; otherwise report the original error.

### 8. Report the Result

Report the PR number, URL, base branch, and draft status returned by GitHub:

```text
✅ Pull request created successfully!
🔢 PR: #[NUMBER]
🔗 URL: [PR_URL]
🎯 Base: [BASE_BRANCH]
📝 Draft: [YES_OR_NO]
```

## Error Handling

Stop with a concise, actionable explanation when an invariant fails. Never claim success until GitHub returns a PR URL or an exact post-error lookup confirms creation.

Do not expose secrets in command output, diffs, generated content, or error reports. Do not bypass authentication, permission, repository policy, or branch protection failures.
