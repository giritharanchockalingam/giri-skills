# Sources

Checked 2026-10-18 (WebFetch of the primary pages; short paraphrases only).

| ID | Source | URL | Used for |
|---|---|---|---|
| S1 | Google, *Site Reliability Engineering*, Chapter 15 "Postmortem Culture: Learning from Failure" (J. Lunney, S. Lueder) | https://sre.google/sre-book/postmortem-culture/ | Blameless postmortems assume everyone acted with good intentions and focus on fixing systems and processes, not people; a blame atmosphere hides incidents. Postmortem triggers include user-visible degradation, data loss, on-call intervention (rollback), long resolution time and monitoring failure. |
| S2 | Google, *The Site Reliability Workbook*, Chapter 10 "Postmortem Culture: Learning from Failure" | https://sre.google/workbook/postmortem-culture/ | Blameful language stifles collaboration; every action item has an owner and a tracking number; an action set that is mostly mitigative should add preventative items. |

## How the skill uses them
- **Blameless check** (S1, S2): `assets/blame-phrases.csv` is this skill's word list of phrasing that assigns fault to a person or uses hindsight judgement. The list is the skill's own; the principle comes from S1 and S2.
- **Owned actions** (S2): an action without an owner is `[TO BE BASELINED — owner: Incident commander]` and fails the `--strict` gate.
- **Prevent / detect / mitigate / process** (S2): the action mix is reported; zero prevent actions is called out.
- **Factor taxonomy**: `assets/factor-taxonomy.csv` is this skill's AI-specific design, not an external standard.
