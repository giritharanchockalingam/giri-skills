# Question Bank — Retail

Scope: omnichannel retailers, grocery, specialty, e-commerce-first brands, wholesale distribution. Buyer personas: CIO, CTO, VP Digital / E-commerce, SVP Supply Chain, VP Stores, CFO, Chief Merchant, Head of Data.

## Typical pains (hypothesis seeds)
| Area | Pattern seen repeatedly | Usually owned by |
|---|---|---|
| Order orchestration | Online/store/marketplace orders routed through brittle OMS integrations; split shipments, cancellations | VP Digital / SVP Supply Chain |
| Inventory accuracy | Store and DC inventory visible late or wrong; promise-to-ship broken at peak | SVP Supply Chain / VP Stores |
| Fulfillment options | Pickup, curbside, ship-from-store added fast and never hardened | VP Digital / VP Stores |
| Peak readiness | Black Friday / holiday scaling incidents; manual war rooms | CIO / CTO |
| Integration estate | Hundreds of interfaces across ERP, OMS, WMS, POS, PIM, loyalty, marketplaces; platform licensing cost rising | VP Apps / CIO |
| Pricing and promo | Promo setup manual; price inconsistencies across channels | Chief Merchant |
| Data and personalization | Customer 360 incomplete; loyalty and marketing on separate truths | Head of Data / CMO |
| Store tech | Aging POS, store-network limits, associate tools | VP Stores |
| Supply chain planning | Forecast accuracy, vendor compliance, transportation visibility | SVP Supply Chain |

## Questions by funnel stage
### Situation
| # | Question | Persona | Listen for |
|---|---|---|---|
| R1 | Walk me through an online order placed for store pickup — every system it touches until the customer leaves with it. | VP Digital | Integration hops, manual steps, timing |
| R2 | How many active integrations run across ERP, OMS, WMS, POS, PIM, and marketplaces, and on what platform(s)? | VP Apps | Inventory size, platform mix, licensing |
| R3 | How many stores, DCs, and channels, and which channels are growing fastest? | CIO / SVP SC | Scale and growth drivers |
| R4 | Which platforms are under contract review or end-of-life in the next 24 months? | CIO | Forcing events |

### Pain
| # | Question | Persona | Listen for |
|---|---|---|---|
| R5 | What went wrong during your last peak, and how was it handled — automation or a war room? | CTO | Incident type, manual effort |
| R6 | Where do you see the most cancellations or substitutions caused by inventory being wrong at the moment of promise? | SVP SC / VP Digital | Promise accuracy, root cause |
| R7 | When a new channel or marketplace is added, how long does integration take and who does it? | VP Apps | Time-to-market, key-person dependency |
| R8 | What do store associates complain about in the tools for fulfillment and inventory? | VP Stores | Adoption and process friction |
| R9 | Which numbers do Finance and Supply Chain argue about every month? | CFO | Data trust |

### Impact
| # | Question | Persona | Listen for |
|---|---|---|---|
| R10 | What did the last peak incident cost — lost orders, overtime, expedited freight, markdowns? Is that from a post-mortem? | CFO / CTO | Figure and source |
| R11 | What is your cancellation or split-shipment rate, and what does each point cost in margin? | VP Digital | Value lever |
| R12 | What are you paying annually for integration platform licensing and the team that runs it? | CIO / VP Apps | Run-rate baseline for a migration case |
| R13 | How much working capital is tied up because inventory accuracy forces safety stock? | SVP SC / CFO | Inventory carrying cost |

### Urgency
| # | Question | Persona | Listen for |
|---|---|---|---|
| R14 | What has to be true before next peak season freeze, and when is the freeze? | CTO | Hard date |
| R15 | Which platform renewal or vendor decision is forcing a choice this year? | CIO | Contract-driven urgency |

### Decision and constraints
| # | Question | Persona | Listen for |
|---|---|---|---|
| R16 | Who owns the decision — IT, Digital, Supply Chain — and how do the three align on priorities? | CIO | Political map |
| R17 | Is the budget in capex for a platform change, or opex for run improvement? | CFO | Funding shape |
| R18 | PCI, consumer privacy, data residency — which constraints apply to any partner? | CISO | Hard gates |
| R19 | What portion of the work could your team own versus a partner, and what is their peak-season availability? | VP Apps | Capacity and freeze calendar |

## Branch table
| If they say | Go to |
|---|---|
| "We're replatforming commerce." | R1, R7, R12; integration volume during replatform is the opportunity |
| "Inventory is the real problem." | R6, R13; probe source-of-truth and event latency |
| "We're happy with our integration platform; it's just expensive." | R12, R15; migration-TCO play, see integration-migration-assessor |
| "We need AI for personalization." | R9, and data readiness; qualify whether Customer 360 exists |

## Pre-reads worth requesting
Interface inventory, peak post-mortem, integration platform contract summary and renewal date, order funnel metrics (cancel, split, promise-miss), store and DC counts by region.
