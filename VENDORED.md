# Vendored / Upstream Skills

50 top public Agent Skills are vendored verbatim under `vendor/<name>/`, each pinned to a commit in `vendor/pins.json` with `UPSTREAM.md` + `LICENSE.upstream` beside it. Catalog with ranking evidence: `catalog/TOP-50.md`. Our own 40 skills wrap some of these by name (security-review, vercel-*, supabase, karpathy-guidelines, superpowers sub-skills, anthropics docx/pdf/pptx/xlsx/skill-creator/mcp-builder/webapp-testing).

## Commands
```bash
python3 scripts/vendor_sync.py            # sync at pinned commits
python3 scripts/vendor_sync.py --update   # move pins to upstream HEAD
python3 scripts/vendor_sync.py --check    # CI: every catalog entry vendored
scripts/install.sh claude                 # installs skills/ AND vendor/
```

## Rules
- Never edit files under `vendor/`; change the pin and re-sync.
- Never copy upstream bodies into `skills/`; wrap by name.
- superpowers sub-skills are also installable as a plugin: `/plugin marketplace add obra/superpowers-marketplace` → `/plugin install superpowers@superpowers-marketplace`.

## Licensing
| Group | Count | Terms |
|---|---|---|
| MIT / Apache-2.0 (LICENSE file or repo README) | 46 | Redistributable with attribution (kept in `LICENSE.upstream`) |
| Anthropic source-available: `docx`, `pdf`, `pptx`, `xlsx` | 4 | Governed by your Anthropic agreement, not OSS. Fine in this private repo for your own use; **do not redistribute publicly** |

Excluded on purpose: trailofbits/skills (CC-BY-SA share-alike), better-auth/skills (no license, repo unreachable), bulk AI-generated collections.

## Pins
See `vendor/pins.json` (repo, path, sha, license, fetched date per skill).
