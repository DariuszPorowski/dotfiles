# Conventional Commits Reference

Use this reference to draft and validate commit messages against [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/). It separates the normative specification from broadly useful defaults. Repository policy may add stricter rules, allowed values, or release behavior.

This reference is sufficient when a repository does not actively use commitlint. Commitlint is not part of the Conventional Commits specification and must not be assumed, installed, or emulated.

## Normative Core

The message structure is:

```text
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

The 1.0.0 specification requires:

1. A noun type followed by an optional parenthesized noun scope, an optional `!`, and exactly `:` plus one space before the description.
2. `feat` for a new feature and `fix` for a bug fix.
3. A non-empty short description immediately after the colon and space.
4. One blank line before an optional free-form body.
5. One blank line before optional footers, whether they follow the description or a body.
6. Footer tokens that use `-` instead of spaces, followed by either `:` and a space or a space and `#`, then a value. `BREAKING CHANGE` is the allowed space-containing exception.
7. Footer values that may span lines and end when the next valid footer token and separator begin.
8. A breaking change marked either by `!` in the prefix or by a `BREAKING CHANGE: <description>` footer.
9. Uppercase `BREAKING CHANGE` when that footer spelling is used. `BREAKING-CHANGE` is a valid synonym.
10. Case-insensitive interpretation of message elements except for uppercase `BREAKING CHANGE`.

The specification does **not** require:

- a fixed universal list of types beyond the required meanings of `feat` and `fix`
- lowercase types or descriptions
- imperative mood
- a 50-, 72-, or 100-character limit
- a scope
- both `!` and a breaking-change footer
- issue references

Those can still be good or enforced repository rules. Describe them accurately as local policy or defaults.

## Optional Commitlint Overlay

The main skill owns the commitlint detection gate.

- When no active commitlint configuration or hook is detected, use this reference alone and do not load or run commitlint.
- When active commitlint usage is detected, also fetch and apply the upstream [`committing-with-commitlint` skill](https://raw.githubusercontent.com/conventional-changelog/commitlint/master/skills/committing-with-commitlint/SKILL.md). Its resolved repository rules add enforceable constraints to this specification.
- A commitlint dependency, Conventional Commit-shaped history, or documentation mention alone does not activate the overlay.
- Do not install commitlint to perform validation. If the repository configures it but the existing executable cannot be resolved, report that deterministic validation was unavailable.

Commitlint can enforce allowed types, required or forbidden scopes, casing, punctuation, and length. It cannot prove that the message truthfully describes the diff, that the change is atomic, or that a breaking effect was correctly understood. Apply both layers when the overlay is active.

## Policy Precedence

Apply rules in this order:

1. The actual semantics of the change must remain truthful.
2. Resolved commitlint rules, only when the main skill detects active commitlint usage.
3. Other explicit repository rules.
4. Stable repository conventions not contradicted by configuration.
5. The defaults in this reference.

Useful policy evidence includes:

- `AGENTS.md`, `CONTRIBUTING.md`, and repository-specific instructions
- release, changelog, or semantic-release configuration
- recent non-merge commit subjects in the affected component

Do not infer a rule from one unusual commit. Sample enough recent subjects to identify a stable pattern, and prefer the affected component's history in a monorepo.

## Default Type Set

When the repository does not define a type set, use this conventional baseline:

| Type | Use when | Do not use when |
| --- | --- | --- |
| `feat` | A user or consumer gains a capability | Only internals, tests, or docs changed |
| `fix` | Incorrect behavior is corrected | Behavior was already correct and code was only reorganized |
| `perf` | Performance improves with evidence in the change or context | The benefit is speculative |
| `refactor` | Internal structure changes without intended behavior change | A defect is fixed or capability added |
| `docs` | Documentation is the deliverable | Docs merely accompany code behavior |
| `test` | Tests or fixtures are the deliverable | Tests prove a feature or fix in the same atomic change |
| `style` | Formatting or other non-semantic source changes | UI styling or behavior changes |
| `build` | Build tooling, packaging, or dependency machinery changes | Only CI workflow behavior changes |
| `ci` | Continuous-integration or delivery automation changes | Product runtime behavior changes |
| `chore` | Narrow maintenance fits no more precise allowed type | The intent is unknown or several changes were mixed |
| `revert` | A prior change is intentionally reversed | Code merely returns to behavior that happens to resemble an older version |

Custom types such as `security`, `deps`, or `release` are valid Conventional Commit types when repository policy allows them. They carry no standard Semantic Versioning meaning unless local release tooling assigns one.

### Type decision order

Ask these questions in order:

1. Does this break a public contract? Mark breaking, then choose the underlying type.
2. Does it add a consumer-visible capability? Use `feat`.
3. Does it correct unintended behavior? Use `fix`.
4. Does it improve performance without changing intended behavior? Use `perf`.
5. Does it only reorganize internals? Use `refactor`.
6. Is the deliverable exclusively docs, tests, formatting, build machinery, or CI? Use that specific type.
7. Is it an intentional reversal? Use `revert` if local policy supports it.
8. Only then consider `chore` or a repository-specific type.

The primary purpose controls the type. A feature with tests and docs is normally `feat`; a bug fix with a regression test is normally `fix`.

## Scope Selection

A scope is a noun naming the affected section of the codebase. Prefer, in order:

1. an enforced scope from repository configuration
2. an established package or component scope in recent history
3. a stable service, command, feature, or subsystem name visible in the codebase
4. no scope

Good scopes survive file moves and help a reader locate ownership: `parser`, `auth`, `cli`, `billing`, or a package name. Avoid filenames, ticket numbers, branch names, invented abbreviations, `global`, and multi-scope lists such as `api,ui`.

Scope is optional under the base specification. Omit it when the change is truly cross-cutting or evidence does not support a stable name.

## Subject Quality

Absent local rules, prefer a subject that:

- starts with an imperative present-tense verb
- states the concrete outcome rather than the editing activity
- uses lowercase after the colon
- has no trailing period
- keeps the full header at or below 72 characters when clarity permits

Prefer `fix(auth): prevent refresh loops for expired sessions` over `fix(auth): update auth code`. Do not sacrifice an essential qualifier merely to meet a non-enforced length preference.

## Bodies

Use a body when the subject cannot carry important verified context. A useful body explains one or more of:

- the prior behavior or problem
- why the change is needed
- the observable impact
- a non-obvious implementation constraint or tradeoff

Do not list files, repeat the subject, paste a changelog, or invent intent. Multi-paragraph bodies are valid.

## Footers and Trailers

Examples of valid footer forms include:

```text
Refs: #123
Closes #456
Reviewed-by: A. Reviewer
Co-authored-by: A. Contributor <contributor@example.com>
BREAKING CHANGE: callers must pass an explicit region
```

Each footer starts after a blank line. A token uses hyphens instead of whitespace; `BREAKING CHANGE` is the exception. A value may continue onto following lines until another valid footer begins.

Use only references and identities present in user input or repository evidence. Prefer the canonical `BREAKING CHANGE:` spelling for tool compatibility even though `BREAKING-CHANGE:` is also valid under the specification.

## Breaking-Change Analysis

A change is breaking when a reasonable existing consumer must change to upgrade successfully. Check these contracts:

| Contract | Breaking signals |
| --- | --- |
| Public API | Removed or renamed exports, incompatible signatures, narrowed accepted input, changed return or error contract |
| CLI | Removed or renamed commands or flags, changed defaults, incompatible output used by scripts |
| Configuration | Removed keys, changed precedence or defaults, newly required values |
| Data | Incompatible schema, migration, serialization, or persisted-state change |
| Integration | Changed routes, events, protocols, payloads, authentication, or extension interfaces |
| Platform | Dropped runtime, operating-system, architecture, or dependency support |
| Documented behavior | Intentional incompatible behavior that consumers are told they can rely on |

Large diffs, internal file moves, private symbol renames, implementation swaps behind a stable contract, and additive optional behavior are not automatically breaking.

Use `!` for visible signaling:

```text
feat(api)!: remove the legacy token endpoint
```

Add a footer when consumers need explicit impact or migration detail:

```text
feat(api)!: remove the legacy token endpoint

BREAKING CHANGE: clients must exchange credentials through `/oauth/token`.
```

If a potential contract is not visible in the evidence, ask rather than assert.

## Atomicity

One commit should have one purpose that can be understood and reverted coherently. Suggest separate commits when changes:

- solve unrelated problems
- affect independent subsystems for different reasons
- combine behavior change with an optional cleanup
- require different types or release signals
- would be safer to review or revert independently

Keep supporting tests, documentation, generated artifacts, migrations, and dependency metadata with the behavior they are required to support.

## Validation Matrix

Validate each layer independently:

| Layer | Question | Failure example |
| --- | --- | --- |
| Syntax | Does the message match the required structure? | `feat(parser) add arrays` lacks a colon and space |
| Commitlint overlay | When active, did the upstream workflow resolve the real configuration and validate the complete message? | Claiming compliance from assumed preset defaults |
| Repository policy | Does it satisfy configured types, scopes, case, and limits? | Valid `feature:` rejected by a `feat`-only type rule |
| Semantics | Does the type describe the actual intent? | `refactor:` for a user-visible bug fix |
| Scope | Is the scope supported and useful? | `fix(misc): ...` where no `misc` component exists |
| Subject | Is the outcome concrete and concise? | `chore: updates` |
| Body | Are all claims useful and evidenced? | Claims a latency reduction with no supporting context |
| Footers | Are trailers separated and well formed? | `BREAKING CHANGE - removed API` |
| Breaking change | Are incompatible consumer effects signaled? | Public API removal with no `!` or footer |
| Atomicity | Can one message truthfully describe the whole change? | Unrelated feature and dependency migration |

Report syntax validity, local-policy compliance, and semantic accuracy separately. Passing one does not prove the others.

## Release Meaning

Under Conventional Commits and Semantic Versioning:

- `fix` normally implies a PATCH release.
- `feat` normally implies a MINOR release.
- a breaking change of any type normally implies a MAJOR release.
- other types have no standard release effect unless local tooling defines one.

Do not promise a release bump without checking the repository's release automation.

## Examples

Minimal feature:

```text
feat(parser): accept trailing commas in arrays
```

Fix with context and issue trailer:

```text
fix(auth): stop refresh retries after session expiry

Expired sessions re-entered the refresh path after validation failed. Stop
after the first failed refresh and return the original authentication error.

Fixes #312
```

Repository maintenance:

```text
build(deps): update the TypeScript toolchain
```

Breaking configuration change:

```text
feat(config)!: require an explicit deployment region

Implicit region selection produced different targets across environments.

BREAKING CHANGE: set `region` in each deployment profile before upgrading.
```

Revert with a trailer:

```text
revert: restore synchronous plugin initialization

The asynchronous path can deadlock when plugins load each other during startup.

Refs: 676104e
```

Syntactically valid but semantically suspect:

```text
chore: add customer export
```

If customer export is a new capability, the accurate type is `feat`. Syntax alone is not enough.
