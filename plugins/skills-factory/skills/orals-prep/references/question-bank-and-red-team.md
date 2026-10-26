# Question Bank and Red Team

## 1. Question-generation sources
| Source | Produces |
|---|---|
| Compliance matrix `P`/`N`/`Q` rows | "How will you meet <requirement>?" — one per row |
| Every `[TO BE BASELINED]` in the proposal | "What is the number?" — answer: how and when it will be baselined |
| Every assumption in the estimate | "What if <assumption> is wrong?" |
| Evaluation criteria | One question per criterion from each evaluator archetype |
| Battle card objections | The alternative's strengths as questions |
| Discovery divergent views | "Your proposal assumes X; our operations team says Y" |
| Standard evaluator set (below) | Baseline coverage |

## 2. Standard evaluator questions by theme
### Understanding and approach
| Question | Answer pattern | Evidence |
|---|---|---|
| "What is the biggest risk to this program, and what would you do about it?" | Name the top risk from the register, its early signal, the mitigation, the owner | Risk register |
| "Why this phasing? Why not faster?" | Gate logic; what each gate de-risks; what faster would cost in risk | Approach section |
| "What do you need from us, and what happens if we cannot provide it?" | Dependency list with dates; day-for-day consequence; alternatives | Dependencies table |
| "What would make you walk away?" | Honest conditions (access, decision latency); shows judgment | Assumptions |

### Team
| Question | Answer pattern | Evidence |
|---|---|---|
| "Will the people in this room be on the engagement?" | Named commitments; continuity clause; what happens on departure | Team section |
| "How much of the work is offshore and how do you manage it?" | Mix by phase; onshore counterparts; overlap hours; security model | Team and governance |
| "What happens if your lead leaves?" | Succession named; knowledge in repo; continuity commitment | Governance |

### Proof
| Question | Answer pattern | Evidence |
|---|---|---|
| "Have you done exactly this before?" | Cleared reference with scale and outcome; what was different; what we learned | Why-us |
| "Can we speak to that client?" | Only if cleared-contactable; otherwise anonymized reference and offer written case | Reference register |
| "What went wrong on a similar program?" | One honest example (anonymized), the cause, the change we made | Lessons |

### Commercial and risk
| Question | Answer pattern | Evidence |
|---|---|---|
| "Why are you more expensive than <alternative>?" | Basis of estimate (scored inventory, P80 contingency explicit); invite like-for-like; levers with risk effects | Pricing basis |
| "What is not included?" | Exclusions list; why; how handled if needed | Pricing exclusions |
| "What triggers a change request?" | Assumption register; threshold; process | SOW assumptions |
| "Will you share risk / fixed price?" | Which phases fixed, which not, and why (inventory confidence) | Commercial model |

### Technical
| Question | Answer pattern | Evidence |
|---|---|---|
| "Why this architecture over <alternative>?" | Options table and scoring; the deciding criterion | ADR-001 |
| "How do you handle cutover and rollback?" | Parallel run, variance tolerance, rollback window, hypercare | Migration method |
| "How do you secure <data class> offshore?" | Residency design, access model, certifications in scope | Security view |
| "What are your NFR commitments?" | Targets with measurement; what is to be baselined with them | NFR table |

### Closing / relationship
| Question | Answer pattern | Evidence |
|---|---|---|
| "Why should we choose you?" | Three win themes, one sentence each, with a number | Exec summary |
| "What would you do in the first 30 days?" | Wave 0 / mobilization plan with dates and what they will see | Plan |
| "Is there anything you want to change in your proposal now?" | Only clarifications; no new scope or price; "we stand by it; we would welcome a clarification on <X>" | — |

## 3. Question bank layout
| # | Question | Theme | Likely asker | Answerer | Answer (≤75 words) | Evidence (slide/page) | Do not say | Confidence |
|---|---|---|---|---|---|---|---|---|

## 4. The hard three
| # | Question | Why it is hard | Honest answer | Mitigation stated | Owner |
|---|---|---|---|---|---|

## 5. Red-team protocol
| Step | Detail |
|---|---|
| Roles | Skeptical evaluator (challenges every number); incumbent-friendly evaluator (defends the status quo); timekeeper/scorer |
| Rounds | Round 1: scripted bank. Round 2: three unscripted questions per red-teamer. Round 3: interrupt mid-presentation |
| Scoring | `assets/orals-rubric.md` per answer and per presenter |
| Log | Every answer >90 s, every new number, every contradiction, every competitor mention, every uncleared reference |
| Fix list | Owner and date per item; re-run the failed items in the next dry run |

## 6. Red-team log layout
| Dry run | Question | Answerer | Time (s) | Issue (long / new number / contradiction / competitor / uncleared / weak) | Fix | Owner | Re-tested (Y/N) |
|---|---|---|---|---|---|---|---|
