# Ops status
- the checker returns one status row per configured endpoint with latency
- an alert is emitted once per transition from ok to down
- GET /api/cron/check answers 200 and writes a run record
- ops_status table exists with RLS
