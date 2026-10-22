# Composition parity fixtures

Produced by `scripts/compose_pipeline.py --bundle` (the Python composer); `tests/compose.test.ts` re-composes each
`input` with `lib/delivery/compose.ts` and expects the same `pipeline`, `decisions` and `notes`. Regenerate after a
change to either composer or to any build skill's `metadata.fits`:

```
S=$(mktemp -d); F=studio/tests/fixtures/compose
python3 scripts/stack_profile.py tests/fixtures/delivery-repo --json $S/js.json
python3 scripts/stack_profile.py tests/fixtures/stack-profile/ts-vercel-supabase --json $S/ts.json
python3 scripts/stack_profile.py tests/fixtures/stack-profile/python-repo --json $S/py.json
python3 scripts/compose_pipeline.py --profile $S/js.json --request-kind feature   --bundle --out $F/feature-js-aws.json
python3 scripts/compose_pipeline.py --profile $S/js.json --request-kind fix       --bundle --out $F/fix-js-aws.json
python3 scripts/compose_pipeline.py --profile $S/ts.json --request-kind hardening --bundle --out $F/hardening-ts-vercel-supabase.json
python3 scripts/compose_pipeline.py --profile $S/py.json --request-kind feature   --bundle --out $F/feature-python.json
python3 scripts/compose_pipeline.py --stacks nextjs,supabase,vercel --request-kind greenfield --bundle --out $F/greenfield-nextjs.json
cd studio && npm run ingest
```
