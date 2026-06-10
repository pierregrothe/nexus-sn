# Schema image export (Kroki)

`nexus schema erd` can emit a shareable image (SVG or PNG) alongside the
Markdown, rendered from the diagram's Mermaid source by a
[Kroki](https://kroki.io) service. The image pastes directly into Teams,
email, Confluence, or Word. Entity boxes carry each table's key fields
(primary key, business columns, and foreign-key references), which makes
rendered diagrams noticeably denser than name-only boxes.

## Usage

```bash
# Markdown only (offline, no Kroki call)
nexus schema erd doc-designer --profile alectri

# Markdown + a shareable image next to it
nexus schema erd doc-designer --profile alectri --image png
nexus schema erd cmdb-bcm --profile alectri --image svg
```

`--image` is opt-in: without it the command stays fully offline and only
writes the `.md`. With it, the `.md` is still written and `<stem>.<fmt>`
is added beside it.

## Output files

The Markdown is written to `{area}-{profile}.md` in the current working
directory by default; pass `-o`/`--output` to choose another path. The image,
when requested, is written as a sibling of the Markdown with the format
extension (for example `doc-designer-alectri.png` next to
`doc-designer-alectri.md`). This repo keeps checked-in ERDs under
`docs/erd/{area}-{profile}.md`; generated images there are git-ignored and
reproducible on demand.

## Options

| Option | Default | Purpose |
| --- | --- | --- |
| `--image {svg,png}` | (off) | Also render a shareable image. SVG is vector (crisp, small); PNG pastes into Office. |
| `--kroki-url URL` | `https://kroki.io` | Kroki endpoint. Also reads `NEXUS_KROKI_URL`. |
| `--kroki-timeout SECONDS` | `60` | Per-request timeout. Raise for very dense diagrams on a slow endpoint. |

## Reliability: prefer a self-hosted Kroki

The **public `kroki.io` instance is shared and can be slow or return HTTP 504
(gateway timeout)** on dense diagrams (large ERDs). It is fine
for quick one-offs and demos, but for reliable or repeated rendering -- and so
that internal table/field names never leave your machine -- run Kroki locally
and point `--kroki-url` at it.

Kroki's Mermaid support is a separate companion container, so run both:

```bash
docker network create kroki-net
docker run -d --name kroki-mermaid --network kroki-net yuzutech/kroki-mermaid
docker run -d --name kroki --network kroki-net \
  -e KROKI_MERMAID_HOST=kroki-mermaid -p 8000:8000 yuzutech/kroki

# then render against the local instance
nexus schema erd doc-designer --profile alectri --image png \
  --kroki-url http://localhost:8000
```

A local instance renders even dense ERDs in a few seconds. Tear it down with
`docker rm -f kroki kroki-mermaid && docker network rm kroki-net`.

## What gets sent

Only the diagram's Mermaid source -- table names, field names and types, and
their edges -- is sent to the configured Kroki endpoint. No record data is
included. With a self-hosted endpoint, nothing leaves the host.

## Formats

SVG and PNG are supported (Kroki's Mermaid renderer does not produce PDF). SVG
is recommended for dense ERDs because it stays crisp at any zoom; PNG is handy
for pasting into tools that do not render SVG.

PNG renders at fixed pixel dimensions decided by the diagram layout -- there
is no DPI or scale knob, and the file carries no DPI metadata -- and the
background is transparent, which can look wrong when pasted into dark-themed
tools. Prefer `--image svg` for large areas and rasterize the SVG yourself if
a specific pixel size is required.
