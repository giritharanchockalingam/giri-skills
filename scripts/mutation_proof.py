#!/usr/bin/env python3
"""Mutation proof: do a skill's own output checks catch a broken deliverable?

For every script-only skill: run it on its happy-path eval fixtures (`run_skill.py --demo`), then corrupt each output
file in several ways and re-run that file's declared checks. A corruption is "caught" when at least one check fails.
A check suite that passes corrupted output is a rubber stamp; this measures it.

Mutations: empty file · keep first 30% of lines · drop one data line from the middle · change one number ·
strip every Markdown heading. Not all apply to every file (e.g. no headings in a CSV).

Usage: python3 scripts/mutation_proof.py [--skills GLOB] [--out DIR]   → prints a table, writes mutation.csv
Exit 0 always (it is a measurement); see the summary line for the detection rate.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_output  # noqa: E402
import skillmeta  # noqa: E402


def mutations(text: str, path: Path) -> dict[str, str]:
    lines = text.splitlines(keepends=True)
    out: dict[str, str] = {"empty": ""}
    if len(lines) > 3:
        out["truncate"] = "".join(lines[: max(1, len(lines) * 3 // 10)])
        mid = len(lines) // 2
        out["drop-line"] = "".join(lines[:mid] + lines[mid + 1:])
    nums = list(re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", text))
    if nums:
        m = nums[len(nums) // 2]
        digits = m.group(0)
        changed = digits[:-1] + str((int(digits[-1]) + 3) % 10)
        out["change-number"] = text[: m.start()] + changed + text[m.end():]
    if path.suffix == ".md" and re.search(r"^#{1,6} ", text, re.M):
        out["strip-headings"] = re.sub(r"^#{1,6} ", "", text, flags=re.M)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", default="skills/*/*")
    ap.add_argument("--out", default="runs/mutation-proof")
    a = ap.parse_args()
    out = (ROOT / a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    skipped = []
    reproduced: dict[str, bool] = {}
    for d in sorted(ROOT.glob(a.skills + "/SKILL.md")):
        sd = d.parent
        key = f"{sd.parent.name}/{sd.name}"
        agent = skillmeta.agent_block(skillmeta.load_skill(sd)) or {}
        if any(st.get("kind") == "llm" for st in agent.get("run") or []):
            skipped.append((key, "has a model step (checks on model text are not deterministic)"))
            continue
        run_dir = out / key.replace("/", "__")
        r = subprocess.run([sys.executable, str(ROOT / "scripts/run_skill.py"), "--demo", key, "--provider", "none", "--out", str(run_dir)],
                           capture_output=True, text=True, cwd=str(ROOT))
        rj = run_dir / "run.json"
        if not rj.exists():
            skipped.append((key, "demo did not run: " + (r.stderr.strip().splitlines() or ["?"])[-1][:80]))
            continue
        run = json.loads(rj.read_text())
        rep = lambda: subprocess.run([sys.executable, str(ROOT / "scripts/run_skill.py"), "--reproduce", str(run_dir)],  # noqa: E731
                                     capture_output=True, text=True, cwd=str(ROOT)).returncode
        clean_reproduces = rep() == 0
        reproduced[key] = clean_reproduces
        by_path: dict[str, list[str]] = {}
        for c in run["checks"]:
            if c["pass"]:  # only mutate files whose checks pass on the real output
                by_path.setdefault(c["path"], []).append(c["check"])
        for p, specs in sorted(by_path.items()):
            fp = Path(p)
            if not fp.is_file():
                continue
            original = fp.read_bytes()
            text = original.decode("utf-8", errors="replace")
            for mname, mtext in mutations(text, fp).items():
                fp.write_text(mtext, encoding="utf-8")
                fails = [s for s in specs if not check_output.run_check(s, str(fp), mode="real", out_dir=str(run_dir), cwd=str(sd))["pass"]]
                audit = clean_reproduces and rep() == 1
                fp.write_bytes(original)
                rows.append({"skill": key, "file": fp.name, "mutation": mname, "caught": bool(fails),
                             "caught_by": fails[0][:60] if fails else "", "checks": len(specs), "caught_by_reproduce": audit})
    with (out / "mutation.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["skill", "file", "mutation", "caught", "caught_by", "checks", "caught_by_reproduce"])
        w.writeheader()
        w.writerows(rows)
    total = len(rows)
    caught = sum(r["caught"] for r in rows)
    by_m: dict[str, list[int]] = {}
    for r in rows:
        by_m.setdefault(r["mutation"], [0, 0, 0])
        by_m[r["mutation"]][0] += r["caught"]
        by_m[r["mutation"]][1] += r["caught"] or r["caught_by_reproduce"]
        by_m[r["mutation"]][2] += 1
    print("| Mutation | Caught by declared checks | Caught with --reproduce audit |\n|---|---|---|")
    for m, (c, c2, n) in sorted(by_m.items()):
        print(f"| {m} | {c}/{n} ({c / n:.0%}) | {c2}/{n} ({c2 / n:.0%}) |")
    both = sum(r["caught"] or r["caught_by_reproduce"] for r in rows)
    print(f"\nclean runs reproduce byte-identically: {sum(reproduced.values())}/{len(reproduced)}"
          + ("" if all(reproduced.values()) else " — not: " + ", ".join(k for k, v in reproduced.items() if not v)))
    print(f"with the audit: {both}/{total} caught ({both / max(1, total):.1%})")
    skills_run = len({r['skill'] for r in rows})
    print(f"\nmutation proof: {skills_run} skills, {total} corruptions, {caught} caught ({caught / max(1, total):.1%}); "
          f"{len(skipped)} skipped; details {out / 'mutation.csv'}")
    for k, why in skipped:
        print(f"  skipped {k}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
