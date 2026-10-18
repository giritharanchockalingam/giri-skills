# HANDOFF
## State: Skills Factory live at https://giri-skills-studio.vercel.app — full lifecycle verified in production (2026-10-18)
Supabase `ysesfztvcexufoogjgth` (sf_* tables only) · Vercel `giri-skills-studio` (Next.js + Python function `api/py/run.py`) · workspace "Giri Skills": 40/40 repo skills imported.

## Verified live (2026-10-18)
| Step | Evidence |
|---|---|
| Sign-in (magic link) | `/auth/callback` exchanges code server-side |
| Import repo skills | 40 drafts in workspace |
| Test run (server) | effort-estimator run 7545be97: scripts pass, llm step skipped (no key) |
| Evaluation | infra-gpu-sizing 3/3 (100%); effort-estimator 1/3 (llm step needs key) |
| Review → approve → publish | infra-gpu-sizing v1 published 18:35 UTC |
| Immutability | DB trigger rejects UPDATE on published version (tested as superuser) |
| API key + consumer API | list, contract, run ac848960 succeeded; outputs hand-checked |

## Defects found by the live run (all fixed in code)
auth callback missing · `trailingSlash` leftover · Admin crash (fn prop to client comp) · root `.gitignore runs/` hid 3 route dirs · ambiguous PostgREST embed (two FKs) → silent 404 · native confirm blocked tab · eval runs counted as failures · consumer API leaked workspace_id/policy/runtime paths.

## Open items (owner)
- Add `ANTHROPIC_API_KEY` in Vercel (Production) → re-run effort-estimator test + evaluation.
- Revoke API key `verify-2026-10-18` after testing.
- Not verified: mobile 390/360 pass of the factory pages; invitations (members are added by email only).

## Next thread starts with
Set the Anthropic key, re-run effort-estimator eval, publish it; then 390px pass of Overview/Skills/Test/Release.
