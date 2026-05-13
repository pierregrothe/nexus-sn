---
name: release
description: >-
  Cut a NEXUS release: validate state on main, compute or accept a CalVer tag
  (YYYY.0M.PATCH), bump version in pyproject.toml / __init__.py / README, update
  CHANGELOG, commit, tag, and push to trigger .github/workflows/release.yml which
  builds the wheel and creates a GitHub Release.
user-invocable: true
disable-model-invocation: true
argument-hint: "[<tag>]   # optional explicit tag e.g. 2026.05.2; otherwise auto-suggested"
allowed-tools: Bash AskUserQuestion Read Edit
effort: low
---

## Purpose

Automate the release-cut workflow. Bumps all version references, commits the
bump, tags main, and pushes. The GitHub Actions release.yml workflow builds the
wheel and creates the GitHub Release automatically.

## Pre-flight (gather state, run in parallel)

- Current branch: !`git rev-parse --abbrev-ref HEAD`
- Working tree: !`git status --porcelain | head -5`
- Main vs origin: !`git fetch origin main --quiet 2>&1 ; git rev-list --count main..origin/main 2>/dev/null`
- Latest tag: !`git tag --list '[0-9][0-9][0-9][0-9].[0-9][0-9].*' | sort -V | tail -3`
- Current version: !`python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['tool']['poetry']['version'])"`

## Compute the suggested tag

CalVer format `YYYY.0M.PATCH`:
- `YYYY` = four-digit year (UTC)
- `0M` = zero-padded two-digit month
- `PATCH` = 1, 2, 3, ... resets to 1 each new month

Algorithm:
- Compute `YYYY.0M` from `date -u +%Y.%m`.
- List existing tags matching `YYYY.0M.*`. If none, suggest `YYYY.0M.1`.
- Otherwise increment the highest PATCH by 1.

If `$ARGUMENTS` is non-empty, treat it as the explicit tag (skip suggestion).

## Wheel filename

Python packaging (PEP 440) normalises the version in wheel filenames by stripping
leading zeros from numeric release segments:

    tag 2026.05.2  ->  wheel nexus_sn-2026.5.2-py3-none-any.whl

Compute `WHEEL_VER` from the tag by removing the leading zero from the month
component: `2026.05.2` -> split on `.` -> `["2026", "05", "2"]` ->
strip leading zero from `[1]` -> `"5"` -> join -> `"2026.5.2"`.

## Validate

Refuse to proceed if any of the following are true:
- Current branch is not `main` -- ask user to switch first.
- Working tree dirty -- ask user to stash or commit first.
- `main` is behind `origin/main` -- ask user to `git pull`.
- The tag already exists locally or on remote (`git ls-remote --tags origin <TAG>`).
- The tag does not match `^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$`.

## Confirm

Show the user a summary before touching any file:

```
Repo:        pierregrothe/nexus-sn
Branch:      main (up to date with origin)
New tag:     <TAG>
Wheel file:  nexus_sn-<WHEEL_VER>-py3-none-any.whl

Files that will change:
  pyproject.toml          version = "<OLD>" -> "<TAG>"
  src/nexus/__init__.py   __version__ = "<OLD>" -> "<TAG>"
  README.md               wheel URLs updated to <TAG> / <WHEEL_VER>
  README.md               CalVer line updated via scripts/sync_readme.py
  CHANGELOG.md            new entry added

Then: git commit, git tag <TAG>, git push origin <TAG>
Triggers: .github/workflows/release.yml
Result:   GitHub Release <TAG> with nexus_sn-<WHEEL_VER>-py3-none-any.whl
```

Use AskUserQuestion:
- Header: "Cut release?"
- Question: "Bump version to <TAG>, commit, tag, and push?"
- Options: "Yes, cut release" / "No, abort"

## Execute (only after explicit yes)

### Step 1: Bump pyproject.toml

Use the Edit tool. Find:
```
version = "<OLD>"
```
Replace with:
```
version = "<TAG>"
```

### Step 2: Bump src/nexus/__init__.py

Use the Edit tool. Find:
```
__version__ = "<OLD>"
```
Replace with:
```
__version__ = "<TAG>"
```

### Step 3: Update README.md wheel URLs

The Install section contains two version-specific strings. Replace both.

Old wheel download URL pattern:
```
pip install https://github.com/pierregrothe/nexus-sn/releases/download/<OLD>/nexus_sn-<OLD_WHEEL_VER>-py3-none-any.whl
```
New:
```
pip install https://github.com/pierregrothe/nexus-sn/releases/download/<TAG>/nexus_sn-<WHEEL_VER>-py3-none-any.whl
```

Old ui wheel pattern:
```
pip install "nexus_sn-<OLD_WHEEL_VER>-py3-none-any.whl[ui]"
```
New:
```
pip install "nexus_sn-<WHEEL_VER>-py3-none-any.whl[ui]"
```

Use the Edit tool for each substitution.

### Step 4: Run scripts/sync_readme.py

```bash
python scripts/sync_readme.py
```

This updates the `CalVer:` line and test count in README.md.
Report what changed (or "already up to date").

### Step 5: Add CHANGELOG entry

Generate the commit summary since the last tag:

```bash
git log <LAST_TAG>..HEAD --oneline
```

If there is no prior tag, use `git log --oneline`.

Prepend a new entry to CHANGELOG.md (after the `# CHANGELOG` heading):

```markdown
## <TAG> -- <YYYY-MM-DD>

<one-line summary per commit from git log above, formatted as a bullet list>
```

Use today's UTC date for `<YYYY-MM-DD>`.
Keep each bullet concise (match the commit subject line).

### Step 6: Run tests

```bash
python .claude/hooks/_venv_run.py pytest -q --tb=short -p no:cacheprovider --override-ini=addopts=
```

If any tests fail, stop and report the failures. Do NOT tag or push with
failing tests. Fix the issue and re-run before proceeding.

### Step 7: Commit the version bump

```bash
git add pyproject.toml src/nexus/__init__.py README.md CHANGELOG.md
git commit -m "chore(release): bump version to <TAG>"
```

Note: Do NOT include `Co-Authored-By` in release commits -- the version bump
is a mechanical step and the tag itself is the attribution artifact.

### Step 8: Tag and push

```bash
git tag <TAG>
git push origin main
git push origin <TAG>
```

Push `main` first so the tag points to an upstream-visible commit.

After the push, surface:
- Workflow URL: `https://github.com/pierregrothe/nexus-sn/actions/workflows/release.yml`
- Expected release URL: `https://github.com/pierregrothe/nexus-sn/releases/tag/<TAG>`

Tell the user to wait ~1-2 min for the workflow to finish. Subsequent `nexus`
launches will auto-detect the new version (24h time-gate; reset early by
removing `~/.nexus/cache/update.last_check`).

## Recovery

**Before any push:** `git tag -d <TAG>` deletes the local tag.
`git reset HEAD~1` undoes the version-bump commit (keep changes staged).

**After tagging but before workflow completes:**
```bash
git push --delete origin <TAG>
git tag -d <TAG>
git reset HEAD~1     # undo bump commit locally
```

**After a bad release:** `gh release delete <TAG> --yes --cleanup-tag`.
To roll back an installed version: `pip install <WHEEL_URL_OF_GOOD_VERSION>`.

## Red flags

- Never push a tag without explicit user confirmation.
- Never tag a non-`main` branch.
- Never use `git push --force` here.
- Never skip Step 6 (tests) -- a tagged release must be green.
- Honour an explicit tag from `$ARGUMENTS`; do not auto-increment it.
  Still validate the format.
