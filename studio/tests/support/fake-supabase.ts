// In-memory stand-in for the slice of the supabase-js query builder the orchestrator uses. Real semantics where they
// matter (filters, upsert conflict + ignoreDuplicates, generated ids); a table can be told to fail its next write.
type Row = Record<string, unknown>;
export class FakeDb {
  tables: Record<string, Row[]> = {};
  failNext: Record<string, string> = {};
  private seq = 0;
  constructor(seed: Record<string, Row[]> = {}) { for (const [t, rows] of Object.entries(seed)) this.tables[t] = rows.map((r) => ({ ...r })); }
  rows(t: string) { return (this.tables[t] ??= []); }
  id() { return `00000000-0000-4000-8000-${String(++this.seq).padStart(12, "0")}`; }
  from(t: string) { return new Query(this, t); }
}
class Query implements PromiseLike<{ data: unknown; error: { message: string } | null }> {
  private filters: [string, unknown][] = [];
  private op: "select" | "insert" | "update" | "upsert" = "select";
  private payload: Row[] = [];
  private patch: Row = {};
  private opts: { onConflict?: string; ignoreDuplicates?: boolean } = {};
  private mode: "many" | "single" | "maybe" = "many";
  private db: FakeDb;
  private t: string;
  constructor(db: FakeDb, t: string) { this.db = db; this.t = t; }
  select(_cols?: string) { return this; }
  eq(c: string, v: unknown) { this.filters.push([c, v]); return this; }
  insert(r: Row | Row[]) { this.op = "insert"; this.payload = [r].flat(); return this; }
  update(p: Row) { this.op = "update"; this.patch = p; return this; }
  upsert(r: Row | Row[], o: { onConflict?: string; ignoreDuplicates?: boolean } = {}) { this.op = "upsert"; this.payload = [r].flat(); this.opts = o; return this; }
  single() { this.mode = "single"; return this; }
  maybeSingle() { this.mode = "maybe"; return this; }
  private run(): { data: unknown; error: { message: string } | null } {
    const rows = this.db.rows(this.t);
    if (this.op !== "select" && this.db.failNext[this.t]) { const message = this.db.failNext[this.t]; delete this.db.failNext[this.t]; return { data: null, error: { message } }; }
    let out: Row[] = [];
    if (this.op === "select") out = rows.filter((r) => this.filters.every(([c, v]) => r[c] === v));
    if (this.op === "insert") for (const r of this.payload) { const n = { id: this.db.id(), ...r }; rows.push(n); out.push(n); }
    if (this.op === "update") for (const r of rows) if (this.filters.every(([c, v]) => r[c] === v)) { Object.assign(r, this.patch); out.push(r); }
    if (this.op === "upsert") {
      const keys = (this.opts.onConflict ?? "id").split(",").map((k) => k.trim());
      for (const r of this.payload) {
        const hit = rows.find((x) => keys.every((k) => x[k] === r[k]));
        if (hit) { if (!this.opts.ignoreDuplicates) { Object.assign(hit, r); out.push(hit); } }
        else { const n = { id: this.db.id(), ...r }; rows.push(n); out.push(n); }
      }
    }
    if (this.mode === "many") return { data: out.map((r) => ({ ...r })), error: null };
    if (out.length > 1 || (this.mode === "single" && !out.length)) return { data: null, error: { message: `expected one row, got ${out.length}` } };
    return { data: out[0] ? { ...out[0] } : null, error: null };
  }
  then<A, B>(ok?: ((v: { data: unknown; error: { message: string } | null }) => A | PromiseLike<A>) | null, bad?: ((e: unknown) => B | PromiseLike<B>) | null) {
    return Promise.resolve().then(() => this.run()).then(ok, bad);
  }
}
