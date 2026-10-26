#!/usr/bin/env python3
"""Fine-tune dataset builder: raw examples -> cleaned, de-duplicated, leak-free chat-format splits.

Usage:
  python3 -I build_dataset.py --examples raw.csv|raw.jsonl --out-dir OUT \
      [--split 0.8,0.1,0.1] [--seed 42] [--min-rows 10] [--max-chars N] [--existing-dir CURRENT]
  python3 -I build_dataset.py --validate-jsonl FILE    # exit 1 unless every line is a valid chat record

Input formats:
  CSV    columns prompt,completion (optional system); other columns are ignored.
  JSONL  one object per line, either {"messages":[{"role":..,"content":..},...]} ending with an
         assistant turn, or {"prompt":..,"completion":..[,"system":..]}. Other keys are ignored.

Pipeline (deterministic):
  1. validate  non-empty prompt and completion; roles in system|user|assistant; last turn assistant;
               total characters <= --max-chars when given. Rejected rows are counted by reason.
  2. normalise whitespace: CRLF -> LF, trailing spaces per line stripped, runs of spaces/tabs -> one
               space, 3+ blank lines -> one blank line, ends trimmed.
  3. dedupe    exact duplicates (identical raw record), then normalised duplicates (casefolded,
               all whitespace collapsed); first occurrence kept.
  4. split     examples are grouped by normalised prompt (all non-assistant turns); groups are
               shuffled with random.Random(seed) and filled train -> val -> test to the ratio
               targets, so one prompt never appears in two splits.
  5. leakage   normalised prompts shared across splits are counted (must be 0; exit 1 otherwise).
  6. length    token estimate = ceil(characters / 4) per example — a heuristic, not a tokenizer.
Extending an existing dataset (--existing-dir DIR with train.jsonl and optionally val.jsonl, test.jsonl from
an earlier build or another tool): existing records are validated, normalised and de-duplicated the same way
and keep their split. A prompt found in more than one existing split is leakage: the group is pinned to the
first split it appears in (train -> val -> test) and its copies elsewhere are moved there and counted. New
examples that duplicate an existing record are dropped ("already in dataset"); a new example whose prompt is
already in a split joins that split; new prompt groups fill the splits toward the ratio targets for the
combined size. No existing record changes split except to repair leakage.
Defaults (stated in data-card.md when used): split 0.8,0.1,0.1; seed 42; min-rows 10; no max-chars.

Outputs: OUT/train.jsonl, OUT/val.jsonl, OUT/test.jsonl ({"messages":[...]} per line),
         OUT/dataset-stats.json, OUT/data-card.md (Source, Cleaning, Splits, Length stats, Known limits).
Exit codes: 0 ok · 1 fewer usable rows than --min-rows, or leakage > 0 · 2 missing or invalid input.
Stdlib only; reads only --examples; writes only into --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import sys
from pathlib import Path

DEFAULTS = {"split": (0.8, 0.1, 0.1), "seed": 42, "min_rows": 10}
SPLITS = ("train", "val", "test")
ROLES = {"system", "user", "assistant"}


class InputError(Exception):
    """A required input is missing or malformed (exit 2)."""


# ------------------------------------------------------------------ text helpers

def normalise_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", ln).rstrip() for ln in s.split("\n")]
    s = "\n".join(lines)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def dedupe_key(s: str) -> str:
    return " ".join(s.split()).casefold()


def est_tokens(messages: list[dict]) -> int:
    return math.ceil(sum(len(m["content"]) for m in messages) / 4)


# ------------------------------------------------------------------ loading

def _record_from_pair(prompt, completion, system=None) -> list[dict]:
    msgs = []
    if system not in (None, ""):
        msgs.append({"role": "system", "content": str(system)})
    msgs.append({"role": "user", "content": "" if prompt is None else str(prompt)})
    msgs.append({"role": "assistant", "content": "" if completion is None else str(completion)})
    return msgs


def load_examples(path: Path) -> tuple[str, list[tuple[int, object]]]:
    """Return (format, [(source_line, messages | error-string)])."""
    if not path.is_file():
        raise InputError(f"examples file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    items: list[tuple[int, object]] = []
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text, newline=""))
        cols = set(reader.fieldnames or [])
        if not {"prompt", "completion"} <= cols:
            raise InputError(f"CSV needs columns prompt,completion; found {sorted(cols)}")
        for row in reader:  # quoted fields may span lines
            items.append((reader.line_num, _record_from_pair(row.get("prompt"), row.get("completion"), row.get("system"))))
        return "csv", items
    if suffix in (".jsonl", ".ndjson"):
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                items.append((i, "invalid JSON"))
                continue
            if not isinstance(obj, dict):
                items.append((i, "not a JSON object"))
            elif "messages" in obj:
                msgs = obj["messages"]
                if not isinstance(msgs, list) or not all(isinstance(m, dict) for m in msgs):
                    items.append((i, "messages is not a list of objects"))
                else:
                    items.append((i, [{"role": str(m.get("role", "")), "content": m.get("content")} for m in msgs]))
            elif "prompt" in obj or "completion" in obj:
                items.append((i, _record_from_pair(obj.get("prompt"), obj.get("completion"), obj.get("system"))))
            else:
                items.append((i, "no messages or prompt/completion keys"))
        return "jsonl", items
    raise InputError(f"examples must be .csv or .jsonl, got {path.name}")


def validate(msgs: list[dict], max_chars: int | None) -> str | None:
    """Reason string when the record is unusable, else None."""
    if not msgs:
        return "no messages"
    for m in msgs:
        if m["role"] not in ROLES:
            return "unknown role"
        if not isinstance(m["content"], str):
            return "non-text content"
    if msgs[-1]["role"] != "assistant":
        return "last turn is not assistant"
    if not any(m["role"] == "user" for m in msgs):
        return "no user turn"
    if any(not m["content"].strip() for m in msgs):
        return "empty prompt or completion"
    if max_chars is not None and sum(len(m["content"]) for m in msgs) > max_chars:
        return "over max_chars"
    return None


def prompt_of(msgs: list[dict]) -> str:
    return "\n".join(m["content"] for m in msgs[:-1])


# ------------------------------------------------------------------ split

def split_groups(keys: list[str], ratios: tuple[float, float, float], seed: int, sizes: dict[str, int],
                 start: dict[str, int] | None = None, total: int | None = None) -> dict[str, str]:
    """Assign each prompt group to a split. Targets: val = round(n*v), test = round(n*t), train = rest.
    With `start` (records already placed per split) and `total` (all records), targets are for the total and
    the new groups fill what remains."""
    n = sum(sizes[k] for k in keys) if total is None else total
    t_val, t_test = round(n * ratios[1]), round(n * ratios[2])
    t_train = n - t_val - t_test
    order = sorted(keys)
    random.Random(seed).shuffle(order)
    targets = {"train": t_train, "val": t_val, "test": t_test}
    filled = {s: (start or {}).get(s, 0) for s in SPLITS}
    assign = {}
    for k in order:
        # first split (train -> val -> test) that still has room; overflow goes to the least-filled ratio
        dest = next((s for s in SPLITS if filled[s] + sizes[k] <= targets[s]), None)
        if dest is None:
            dest = min(SPLITS, key=lambda s: (filled[s] - targets[s], SPLITS.index(s)))
        assign[k] = dest
        filled[dest] += sizes[k]
    return assign


def stats(values: list[int]) -> dict:
    if not values:
        return {"examples": 0, "min": 0, "mean": 0, "p50": 0, "p95": 0, "max": 0, "total": 0}
    v = sorted(values)

    def pct(p: float) -> int:  # nearest-rank percentile
        return v[max(1, math.ceil(p / 100 * len(v))) - 1]
    return {"examples": len(v), "min": v[0], "mean": round(sum(v) / len(v), 1), "p50": pct(50),
            "p95": pct(95), "max": v[-1], "total": sum(v)}


# ------------------------------------------------------------------ build

def parse_split(s: str | None) -> tuple[tuple[float, float, float], bool]:
    if s is None:
        return DEFAULTS["split"], True
    try:
        parts = tuple(float(x) for x in s.split(","))
    except ValueError:
        raise InputError(f"--split must be three numbers train,val,test; got {s!r}") from None
    if len(parts) != 3 or any(p < 0 for p in parts) or abs(sum(parts) - 1.0) > 1e-6 or parts[0] <= 0:
        raise InputError(f"--split ratios must be 3 non-negative numbers summing to 1 with train > 0; got {s!r}")
    return parts, False


def load_existing(folder: Path, max_chars: int | None) -> dict:
    """Existing split files -> validated, normalised, de-duplicated records pinned to one split each."""
    if not folder.is_dir():
        raise InputError(f"existing dataset folder not found: {folder}")
    if not (folder / "train.jsonl").is_file():
        raise InputError(f"existing dataset folder needs train.jsonl: {folder}")
    read, rejected, files = {}, {}, {}
    seen, pinned, records = set(), {}, []
    dups = moved = 0
    moved_groups: set[str] = set()
    for s in SPLITS:
        f = folder / f"{s}.jsonl"
        if not f.is_file():
            read[s] = 0
            continue
        files[s] = hashlib.sha256(f.read_bytes()).hexdigest()
        _, items = load_examples(f)
        read[s] = len(items)
        for _, rec in items:
            reason = rec if isinstance(rec, str) else validate(rec, max_chars)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            clean = [{"role": m["role"], "content": normalise_ws(m["content"])} for m in rec]
            key = "\x1f".join(f"{m['role']}:{dedupe_key(m['content'])}" for m in clean)
            if key in seen:
                dups += 1
                continue
            seen.add(key)
            pk = dedupe_key(prompt_of(clean))
            dest = pinned.setdefault(pk, s)
            if dest != s:
                moved += 1
                moved_groups.add(pk)
            records.append({"line": 0, "messages": clean, "prompt_key": pk, "split": dest, "norm_key": key})
    return {"dir": folder.name, "files_sha256": files, "records_read": read, "rejected": dict(sorted(rejected.items())),
            "duplicates_removed": dups, "leakage_groups_repaired": len(moved_groups),
            "records_moved_to_repair_leakage": moved, "pinned": pinned, "records": records}


def build(examples: Path, split: str | None, seed: int | None, min_rows: int | None, max_chars: int | None,
          existing_dir: Path | None = None) -> dict:
    ratios, split_default = parse_split(split)
    seed_default, min_default = seed is None, min_rows is None
    seed = DEFAULTS["seed"] if seed is None else seed
    min_rows = DEFAULTS["min_rows"] if min_rows is None else min_rows
    if min_rows < 1:
        raise InputError("--min-rows must be >= 1")
    if max_chars is not None and max_chars < 1:
        raise InputError("--max-chars must be >= 1")
    ex = load_existing(existing_dir, max_chars) if existing_dir is not None else None
    fmt, items = load_examples(examples)

    rejected: dict[str, int] = {}
    valid: list[tuple[int, list[dict], str]] = []
    for line, rec in items:
        reason = rec if isinstance(rec, str) else validate(rec, max_chars)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        raw = json.dumps(rec, sort_keys=True, ensure_ascii=False)
        valid.append((line, rec, raw))

    seen_exact, seen_norm = set(), set()
    exact_dups = norm_dups = changed_ws = in_existing = 0
    existing_keys = {r["norm_key"] for r in ex["records"]} if ex else set()
    kept: list[dict] = []
    for line, rec, raw in valid:
        if raw in seen_exact:
            exact_dups += 1
            continue
        seen_exact.add(raw)
        clean = [{"role": m["role"], "content": normalise_ws(m["content"])} for m in rec]
        key = "\x1f".join(f"{m['role']}:{dedupe_key(m['content'])}" for m in clean)
        if key in existing_keys:
            in_existing += 1
            continue
        if key in seen_norm:
            norm_dups += 1
            continue
        seen_norm.add(key)
        if clean != rec:
            changed_ws += 1
        kept.append({"line": line, "messages": clean, "prompt_key": dedupe_key(prompt_of(clean))})

    prior = ex["records"] if ex else []
    usable = len(kept) + len(prior)
    groups: dict[str, int] = {}
    for k in [*prior, *kept]:
        groups[k["prompt_key"]] = groups.get(k["prompt_key"], 0) + 1
    multi = sum(1 for v in groups.values() if v > 1)

    out_splits: dict[str, list[dict]] = {s: [] for s in SPLITS}
    added = {s: 0 for s in SPLITS}
    if usable >= min_rows:
        pinned = ex["pinned"] if ex else {}
        for k in prior:
            out_splits[k["split"]].append(k)
        new_sizes: dict[str, int] = {}
        for k in kept:
            if k["prompt_key"] not in pinned:
                new_sizes[k["prompt_key"]] = new_sizes.get(k["prompt_key"], 0) + 1
        start = {s: len(out_splits[s]) + sum(1 for k in kept if pinned.get(k["prompt_key"]) == s) for s in SPLITS}
        assign = dict(pinned)
        assign.update(split_groups(list(new_sizes), ratios, seed, new_sizes, start=start, total=usable)
                      if ex else split_groups(list(groups), ratios, seed, groups))
        for k in kept:
            out_splits[assign[k["prompt_key"]]].append(k)
            added[assign[k["prompt_key"]]] += 1
    prompt_sets = {s: {k["prompt_key"] for k in out_splits[s]} for s in SPLITS}
    leakage = (len(prompt_sets["train"] & prompt_sets["val"]) + len(prompt_sets["train"] & prompt_sets["test"])
               + len(prompt_sets["val"] & prompt_sets["test"]))

    existing = None
    if ex:
        existing = {"dir": ex["dir"], "files_sha256": ex["files_sha256"], "records_read": ex["records_read"],
                    "rejected": ex["rejected"], "duplicates_removed": ex["duplicates_removed"],
                    "leakage_groups_repaired": ex["leakage_groups_repaired"],
                    "records_moved_to_repair_leakage": ex["records_moved_to_repair_leakage"],
                    "kept": {s: sum(1 for k in prior if k["split"] == s) for s in SPLITS},
                    "new_already_in_dataset": in_existing, "new_added": added}
    return {
        **({"existing": existing} if existing else {}),
        "source": {"file": examples.name, "format": fmt,
                   "sha256": hashlib.sha256(examples.read_bytes()).hexdigest(), "records_read": len(items)},
        "parameters": {
            "split": {"value": list(ratios), "default": split_default},
            "seed": {"value": seed, "default": seed_default},
            "min_rows": {"value": min_rows, "default": min_default},
            "max_chars": {"value": max_chars, "default": max_chars is None},
        },
        "cleaning": {"rejected": dict(sorted(rejected.items())), "rejected_total": sum(rejected.values()),
                     "whitespace_normalised": changed_ws, "exact_duplicates_removed": exact_dups,
                     "normalised_duplicates_removed": norm_dups, "usable": usable,
                     "prompts_with_multiple_completions": multi},
        "splits": {s: len(out_splits[s]) for s in SPLITS},
        "leakage_prompts_across_splits": leakage,
        "length_tokens_estimate": {s: stats([est_tokens(k["messages"]) for k in out_splits[s]]) for s in SPLITS},
        "verdict": "ok" if usable >= min_rows and leakage == 0 else
                   ("too few usable rows" if usable < min_rows else "leakage detected"),
        "_records": out_splits,
    }


# ------------------------------------------------------------------ outputs

def _p(param: dict, fmt=str) -> str:
    v = param["value"]
    shown = "none" if v is None else fmt(v)
    return f"{shown} (default)" if param["default"] else f"{shown} (supplied)"


def render_card(r: dict) -> str:
    src, par, cl, sp = r["source"], r["parameters"], r["cleaning"], r["splits"]
    rej = ", ".join(f"{k}: {v}" for k, v in cl["rejected"].items()) or "none"
    lines = [
        "# Data card — fine-tune dataset", "",
        "## Source", "",
        f"- File: `{src['file']}` ({src['format']}), {src['records_read']} records read.",
        f"- Checksum (sha256): `{src['sha256']}`",
        f"- Parameters: split {_p(par['split'], lambda v: ','.join(str(x) for x in v))}; "
        f"seed {_p(par['seed'])}; min_rows {_p(par['min_rows'])}; max_chars {_p(par['max_chars'])}.",
        "- Owner, licence and consent for the source examples: [TO BE BASELINED — owner: Data owner]",
    ]
    ex = r.get("existing")
    if ex:
        rd = ex["records_read"]
        lines += [f"- Extends the existing dataset `{ex['dir']}/` ({rd['train']} train, {rd['val']} val, {rd['test']} test "
                  f"records read); existing records keep their split.",
                  f"- Existing set audit: {sum(ex['rejected'].values())} invalid record(s) dropped, "
                  f"{ex['duplicates_removed']} duplicate(s) removed, {ex['leakage_groups_repaired']} leaking prompt "
                  f"group(s) repaired by moving {ex['records_moved_to_repair_leakage']} record(s) to the group's first split.",
                  f"- New examples already in the dataset (dropped): {ex['new_already_in_dataset']}."]
    lines += [
        "",
        "## Cleaning", "",
        "| Step | Records |", "|---|---|",
        f"| Rejected by validation ({rej}) | {cl['rejected_total']} |",
        f"| Whitespace normalised (kept) | {cl['whitespace_normalised']} |",
        f"| Exact duplicates removed | {cl['exact_duplicates_removed']} |",
        f"| Normalised duplicates removed | {cl['normalised_duplicates_removed']} |",
        f"| Usable examples | {cl['usable']} |",
        f"| Prompts with more than one completion (kept together in one split) | "
        f"{cl['prompts_with_multiple_completions']} |", "",
        "## Splits", "",
    ]
    if r["verdict"] == "too few usable rows":
        lines += [f"Not built: {cl['usable']} usable examples is below min_rows "
                  f"{par['min_rows']['value']}. Add examples and re-run.", ""]
    if ex:
        lines += ["| Split | Existing kept | New added | Examples |", "|---|---|---|---|"]
        lines += [f"| {s} | {ex['kept'][s]} | {ex['new_added'][s]} | {sp[s]} |" for s in SPLITS]
    else:
        lines += ["| Split | Examples |", "|---|---|"] + [f"| {s} | {sp[s]} |" for s in SPLITS]
    lines += ["", f"Leakage (normalised prompts shared across splits): {r['leakage_prompts_across_splits']}.", "",
              "## Length stats", "",
              "Token counts are an **estimate** (characters ÷ 4, rounded up), not a model tokenizer.", "",
              "| Split | Examples | Min | Mean | P50 | P95 | Max | Total |", "|---|---|---|---|---|---|---|---|"]
    for s in SPLITS:
        t = r["length_tokens_estimate"][s]
        lines.append(f"| {s} | {t['examples']} | {t['min']} | {t['mean']} | {t['p50']} | {t['p95']} | {t['max']} | {t['total']} |")
    lines += ["", "## Known limits", "",
              "- Token lengths are estimated; check against the target model's tokenizer and context limit before training.",
              "- Duplicates are exact or whitespace/case-normalised only; paraphrases and near-duplicates are not detected.",
              "- No PII, toxicity, licensing or factual-quality screening is done here; run `pii-data-inventory` on the source first.",
              "- Splits are random by prompt group, not stratified by task, label or difficulty.",
              "- A small test split gives wide confidence intervals; treat its scores as indicative.", ""]
    return "\n".join(lines)


def write_outputs(r: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for s in SPLITS:
        with (out / f"{s}.jsonl").open("w", encoding="utf-8") as f:
            for k in r["_records"][s]:
                f.write(json.dumps({"messages": k["messages"]}, ensure_ascii=False) + "\n")
    public = {k: v for k, v in r.items() if not k.startswith("_")}
    (out / "dataset-stats.json").write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "data-card.md").write_text(render_card(r), encoding="utf-8")


def validate_jsonl(path: Path) -> int:
    """Exit 0 when every line is {"messages":[...]} with user/assistant turns ending in assistant."""
    if not path.is_file():
        print(f"missing: {path}", file=sys.stderr)
        return 1
    bad = n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        n += 1
        try:
            obj = json.loads(line)
            msgs = obj["messages"]
            ok = (set(obj) == {"messages"} and isinstance(msgs, list)
                  and validate([{"role": m["role"], "content": m["content"]} for m in msgs], None) is None)
        except (json.JSONDecodeError, KeyError, TypeError):
            ok = False
        bad += not ok
    print(f"{path.name}: {n} records, {bad} invalid")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--examples", type=Path, help="raw examples (.csv prompt,completion or .jsonl)")
    ap.add_argument("--out-dir", type=Path, help="directory for the split files and data card")
    ap.add_argument("--split", help="train,val,test ratios summing to 1 (default 0.8,0.1,0.1)")
    ap.add_argument("--seed", type=int, help="shuffle seed (default 42)")
    ap.add_argument("--min-rows", type=int, help="minimum usable examples (default 10)")
    ap.add_argument("--max-chars", type=int, help="reject examples longer than this many characters")
    ap.add_argument("--existing-dir", type=Path, help="folder with the current train/val/test.jsonl to extend")
    ap.add_argument("--validate-jsonl", type=Path, metavar="FILE", help="check FILE is valid chat-format JSONL")
    args = ap.parse_args(argv)
    if args.validate_jsonl:
        return validate_jsonl(args.validate_jsonl)
    if not args.examples or not args.out_dir:
        ap.error("--examples and --out-dir are required")
    try:
        r = build(args.examples, args.split, args.seed, args.min_rows, args.max_chars, args.existing_dir)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_outputs(r, args.out_dir)
    print(f"usable {r['cleaning']['usable']}; splits {r['splits']}; leakage {r['leakage_prompts_across_splits']}; "
          f"verdict {r['verdict']}")
    if r["verdict"] != "ok":
        print(f"error: {r['verdict']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
