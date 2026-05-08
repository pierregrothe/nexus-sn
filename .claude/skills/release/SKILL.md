---
name: release
description: >-
  Cut a NEXUS release: validate state on main, compute or accept a CalVer tag
  (YYYY.0M.PATCH), tag and push to trigger .github/workflows/release.yml which
  builds the wheel and creates a GitHub Release. Auto-update consumes that
  release on the next launch.
user-invocable: true
disable-model-invocation: true
argument-hint: "[<tag>]   # optional explicit tag e.g. 2026.05.1; otherwise auto-suggested"
allowed-tools: Bash AskUserQuestion
effort: low
---

## Purpose

Automate the post-merge step from PR #8 (ADR-020). The auto-updater fetches
GitHub Releases, downloads the attached wheel, and re-execs. This skill
creates that release.

## Pre-flight (gather state)

Run these in parallel before deciding:

- Current branch: !`git rev-parse --abbrev-ref HEAD`
- Working tree: !`git status --porcelain | head -5`
- Main vs origin: !`git fetch origin main --quiet 2>&1 ; git rev-list --count main..origin/main 2>/dev/null`
- Latest tag: !`git tag --list '[0-9][0-9][0-9][0-9].[0-9][0-9].*' | sort -V | tail -3`

## Compute the suggested tag

CalVer format is `YYYY.0M.PATCH`:
- `YYYY` = four-digit year (UTC)
- `0M` = zero-padded month
- `PATCH` = 1, 2, 3, ... reset to 1 each month

Algorithm:
- Compute `YYYY.0M` from `date -u +%Y.%m`.
- List tags matching `YYYY.0M.*`. If empty, suggest `YYYY.0M.1`.
- Otherwise, take the max PATCH and add 1.

If `$ARGUMENTS` is non-empty, treat it as the explicit tag to use and skip the
suggestion.

## Validate

Refuse to proceed if any of these are true:
- Current branch is not `main` -- ask user to switch first.
- Working tree dirty -- ask user to stash or commit.
- `main` is behind `origin/main` -- ask user to `git pull`.
- The tag already exists locally or on remote (`git ls-remote --tags origin <tag>`).
- The tag does not match `^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$` -- the release.yml
  pattern is `[0-9][0-9][0-9][0-9].[0-9][0-9].[0-9]*`, so anything outside
  CalVer will silently not trigger the workflow.

## Confirm

Show the user:

```
Repo:        pierregrothe/nexus-sn
Branch:      main (up to date with origin)
New tag:     <TAG>
Will:        git tag <TAG> && git push origin <TAG>
Triggers:    .github/workflows/release.yml
Result:      GitHub Release <TAG> with nexus_sn-<TAG>-py3-none-any.whl attached
```

Use AskUserQuestion with one yes/no question:
- Header: "Cut release?"
- Question: "Tag main as <TAG> and push to trigger the release workflow?"
- Options: "Yes, cut release" / "No, abort"

## Execute (only after explicit yes)

```bash
git tag <TAG>
git push origin <TAG>
```

Do NOT add `-a` (annotated tag) unless requested -- the release.yml only
matches lightweight tags by ref. The release notes come from the workflow's
`gh release create --notes` argument, not the tag message.

After the push, surface:

- Workflow URL: `https://github.com/pierregrothe/nexus-sn/actions/workflows/release.yml`
- Expected release URL: `https://github.com/pierregrothe/nexus-sn/releases/tag/<TAG>`

Tell the user to wait for the workflow to finish (~1-2 min) before the
release appears, and that subsequent `nexus` launches will auto-detect the
new version (24h time-gate; reset by removing
`~/.nexus/cache/update.last_check`).

## Recovery

If the user wants to abort BEFORE pushing:
- `git tag -d <TAG>` (deletes the local tag).

If the user wants to abort AFTER pushing but BEFORE the workflow completes:
- `git push --delete origin <TAG>` and `git tag -d <TAG>`.
- Cancel the running workflow via the URL above.

If the workflow ran but the release is bad:
- Manually `gh release delete <TAG> --yes --cleanup-tag` or have the user
  set `NEXUS_AUTO_UPDATE=0` and `pip install nexus-sn==<good-version>` to
  roll back. Do NOT delete the tag without confirming the user wants to.

## Red flags

- Never push a tag without explicit user confirmation.
- Never tag a non-`main` branch.
- Never use `git push --force` here.
- Do not auto-bump or guess the patch number when the user passed a tag --
  honour what they typed (still validate the format).
