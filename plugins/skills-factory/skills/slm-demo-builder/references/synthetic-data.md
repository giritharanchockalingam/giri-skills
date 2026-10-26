# Synthetic Data for Demos

Goal: data realistic enough to tell the story, generated deterministically, free of real PII, with planted edge cases.

## Approach
| Step | Practice |
|---|---|
| Entity model | List entities and relationships (customers, orders, tickets, policies, invoices); 3–8 entities is enough |
| Volumes | Enough rows for search to feel real (hundreds to low thousands); not enough to slow the demo |
| Generation | Seeded random generator (fixed seed → identical dataset on every reset); templates with vocab lists; optional LLM-generated free text for documents, reviewed once and frozen |
| Realism rules | Plausible distributions (a few big customers, many small), dates within the last 90 days relative to a fixed "demo date", consistent ids across entities, domain vocabulary from the vertical |
| Planted cases | 3–5 scripted records that drive the talk track: the clear win, the ambiguous case, the out-of-scope question, the policy conflict, the approval-needed action |
| PII rules | Fictional names from a curated list; addresses and phone numbers syntactically valid but reserved/non-routable; no real company names; no real employees |
| Documents | Policies, contracts, manuals generated from outlines; include headings and versions so RAG citations look real; include one outdated version to show freshness handling |
| Storage | CSV/JSON in repo under `demo-data/<demo>/`; loader script; reset = reload |
| Labeling | UI footer: "Sample data — generated for demonstration" |

## Generator skeleton (Python, stdlib)
```python
import csv, random, datetime as dt
SEED = 42
rng = random.Random(SEED)
DEMO_DATE = dt.date(2026, 1, 15)             # fixed reference date
FIRST = ["Avery", "Jordan", "Priya", "Mateo", "Lena"]   # curated fictional names
LAST = ["Okafor", "Lindqvist", "Nakamura", "Castillo", "Byrne"]
def customer(i):
    return {"customer_id": f"C{i:05d}", "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "segment": rng.choices(["enterprise", "mid", "small"], weights=[1, 3, 6])[0],
            "created": (DEMO_DATE - dt.timedelta(days=rng.randint(1, 900))).isoformat()}
rows = [customer(i) for i in range(1, 501)]
rows[7].update({"segment": "enterprise", "name": "Priya Okafor"})   # planted: the clear-win case
with open("customers.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
```

## Checklist
- [ ] Seeded; regenerates identically
- [ ] Planted cases documented in the spec with ids
- [ ] No real names, companies, or contact details
- [ ] Dates relative to a fixed demo date
- [ ] Loader and reset scripts exist
