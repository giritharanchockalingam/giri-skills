# Mermaid C4 Templates

Replace placeholders. Keep names identical to those used in the document text and integration map. Each diagram gets a caption line beneath it: `*Figure n — <what it shows>; as of <date>; sources: <…>*`.

## C1 — System context
```mermaid
C4Context
  title System context — <Client> <Initiative> (target state)
  Person(user1, "<Primary user role>", "<what they do>")
  Person_Ext(partner1, "<External party>", "<relationship>")
  System(core, "<Solution name>", "<one-line purpose>")
  System_Ext(sys1, "<External system 1>", "<e.g., ERP>")
  System_Ext(sys2, "<External system 2>", "<e.g., SIS / OMS / MES / PSS>")
  System_Ext(idp, "Identity provider", "<e.g., corporate IdP> [TO BE BASELINED — owner: <role>]")
  Rel(user1, core, "Uses", "HTTPS")
  Rel(core, sys1, "Reads/writes <data>", "REST / events")
  Rel(core, sys2, "Publishes <events>", "Async")
  Rel(partner1, core, "Calls <API>", "REST, OAuth2")
  Rel(core, idp, "Authenticates via", "OIDC")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## C2 — Container
```mermaid
C4Container
  title Container view — <Solution name> (target state)
  Person(user1, "<User role>")
  System_Boundary(sol, "<Solution name>") {
    Container(web, "<Web / portal>", "<framework placeholder>", "User-facing UI")
    Container(gw, "API gateway", "<product or [TO BE BASELINED — owner: <role>]>", "AuthN/Z, routing, rate limits, analytics")
    Container(svc1, "<Domain service A>", "<runtime>", "<responsibility>")
    Container(svc2, "<Domain service B>", "<runtime>", "<responsibility>")
    Container(events, "Event backbone", "<e.g., managed streaming>", "Async integration, replay, DLQ")
    ContainerDb(db1, "<Operational store>", "<DB>", "<data owned>")
    Container(obs, "Observability", "<logs/metrics/traces>", "Correlation IDs, SLO dashboards")
  }
  System_Ext(sys1, "<External system 1>")
  System_Ext(sys2, "<External system 2>")
  Rel(user1, web, "Uses", "HTTPS")
  Rel(web, gw, "Calls", "REST/JSON")
  Rel(gw, svc1, "Routes", "REST")
  Rel(gw, svc2, "Routes", "REST")
  Rel(svc1, db1, "Reads/writes", "SQL/TLS")
  Rel(svc1, events, "Publishes <event>", "Async")
  Rel(svc2, events, "Subscribes <event>", "Async")
  Rel(svc2, sys1, "Syncs <entity>", "REST")
  Rel(events, sys2, "Delivers <event>", "Connector")
  Rel(svc1, obs, "Emits telemetry")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## C3 — Component (critical container only)
```mermaid
C4Component
  title Component view — <Domain service A>
  Container_Boundary(svc1, "<Domain service A>") {
    Component(api, "API layer", "<framework>", "Validation, authZ, request mapping")
    Component(app, "Application services", "<language>", "Use-case orchestration, idempotency keys")
    Component(dom, "Domain model", "<language>", "Business rules")
    Component(repo, "Repository", "<ORM/driver>", "Persistence, outbox")
    Component(pub, "Event publisher", "<client lib>", "Outbox → event backbone")
  }
  ContainerDb(db1, "<Operational store>", "<DB>")
  Container(events, "Event backbone")
  Rel(api, app, "Invokes")
  Rel(app, dom, "Uses")
  Rel(app, repo, "Persists via")
  Rel(repo, db1, "SQL/TLS")
  Rel(repo, pub, "Outbox poll")
  Rel(pub, events, "Publishes")
```

## Deployment
```mermaid
C4Deployment
  title Deployment — <Solution name> — production (target)
  Deployment_Node(cloud, "<Cloud / DC> [TO BE BASELINED — owner: <role>]", "Region: <region>") {
    Deployment_Node(vpc, "Network boundary", "Private subnets, egress control") {
      Deployment_Node(k8s, "Compute", "<managed k8s / serverless>") {
        Container(gw, "API gateway")
        Container(svc1, "<Domain service A>", "", "min 2 replicas, HPA to <n>")
        Container(svc2, "<Domain service B>")
      }
      Deployment_Node(data, "Data tier", "Managed services") {
        ContainerDb(db1, "<Operational store>", "", "Multi-AZ, PITR, RPO <n> min [TO BE BASELINED — owner: <role>]")
        Container(events, "Event backbone", "", "Replication factor 3")
      }
    }
  }
  Deployment_Node(dr, "DR region", "<region>") {
    ContainerDb(db1r, "<Operational store> replica", "", "RTO <n> h [TO BE BASELINED — owner: <role>]")
  }
  Rel(db1, db1r, "Async replication")
```

## Integration flow (optional, for the integration map)
```mermaid
flowchart LR
  subgraph Sources
    S1[<Source system 1>]
    S2[<Source system 2>]
  end
  subgraph Platform
    GW[API gateway]
    EV[(Event backbone)]
    MFT[Managed file transfer]
  end
  subgraph Targets
    T1[<Target system 1>]
    T2[<Target system 2>]
  end
  S1 -- "INT-001 sync REST" --> GW --> T1
  S2 -- "INT-002 event" --> EV --> T2
  S1 -- "INT-003 batch file nightly" --> MFT --> T2
```

## Critical flow (sequence)
```mermaid
sequenceDiagram
  autonumber
  participant U as <User / caller>
  participant GW as API gateway
  participant A as <Domain service A>
  participant DB as <Operational store>
  participant EV as Event backbone
  participant X as <External system>
  U->>GW: POST /<resource> (OAuth2 token)
  GW->>GW: Validate token, rate limit, correlation-id
  GW->>A: Forward request
  A->>DB: Write (tx + outbox)
  A-->>GW: 201 Created
  GW-->>U: 201 + id
  A->>EV: Publish <event> (from outbox)
  EV->>X: Deliver <event>
  X-->>EV: Ack / retry / DLQ
```

## Migration wave timeline
```mermaid
gantt
  title Migration waves — <Client> (indicative; dates [TO BE BASELINED — owner: <role>])
  dateFormat  YYYY-MM-DD
  section Wave 0 — Foundation
  Landing zone, CI/CD, observability, harness :w0, 2026-01-01, 6w
  section Wave 1 — Prove pattern
  <n> simple interfaces, parallel run, cutover :w1, after w0, 6w
  section Wave 2
  <n> medium interfaces :w2, after w1, 8w
  section Wave 3
  <n> complex interfaces :w3, after w2, 10w
  section Wave 4 — Long tail and decommission
  Remaining, legacy decommission :w4, after w3, 6w
```
