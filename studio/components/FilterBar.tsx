"use client";
import { VERDICT_FILTERS, type VerdictFilter } from "@/lib/verdict";

interface Option<T extends string> { key: T; label: string }

/**
 * One filter: single-select chips on desktop, a native <select> on mobile.
 * Both are rendered; CSS shows one at a time (.only-desktop / .only-mobile).
 */
export function ChoiceFilter<T extends string>({ id, label, options, value, onChange, allLabel = "All" }: {
  id: string; label: string; options: readonly Option<T>[]; value: T | "all"; onChange: (next: T | "all") => void; allLabel?: string;
}) {
  return (
    <>
      <div className="chip-group only-desktop" role="group" aria-label={label}>
        <span className="chip-label">{label}</span>
        <button type="button" className="chip" aria-pressed={value === "all"} onClick={() => onChange("all")}>{allLabel}</button>
        {options.map((o) => (
          <button key={o.key} type="button" className="chip" aria-pressed={value === o.key} onClick={() => onChange(o.key)}>{o.label}</button>
        ))}
      </div>
      <div className="select-field only-mobile">
        <label htmlFor={id}>{label}</label>
        <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value as T | "all")}>
          <option value="all">{allLabel}</option>
          {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
    </>
  );
}

export function DomainFilter({ domains, value, onChange, id = "domain" }: { domains: readonly string[]; value: string; onChange: (v: string) => void; id?: string }) {
  return (
    <ChoiceFilter id={id} label="Domain" allLabel="All domains" value={value as string | "all"} onChange={onChange}
      options={domains.map((d) => ({ key: d, label: d }))} />
  );
}

/** Verdict filter. Desktop chips show the four plain verdicts; the select adds the composite "needs …" groups. */
export function VerdictFilterControl({ value, onChange, id = "verdict" }: { value: VerdictFilter; onChange: (v: VerdictFilter) => void; id?: string }) {
  // Desktop chips stay short: the composite "needs a better description / stronger instructions" groups are reached
  // from the summary cards (and the mobile select); when one is active it appears as a pressed chip.
  const chips = VERDICT_FILTERS.filter((f) => f.key === "needs-work" || (f.codes && f.codes.length === 1));
  const active = VERDICT_FILTERS.find((f) => f.key === value);
  const extra = active && !chips.includes(active) && active.key !== "all" ? active : null;
  return (
    <>
      <div className="chip-group only-desktop" role="group" aria-label="Verdict">
        <span className="chip-label">Verdict</span>
        <button type="button" className="chip" aria-pressed={value === "all"} onClick={() => onChange("all")}>All</button>
        {extra && <button type="button" className="chip" aria-pressed="true" onClick={() => onChange("all")}>{extra.label} ×</button>}
        {chips.map((f) => (
          <button key={f.key} type="button" className="chip" aria-pressed={value === f.key} onClick={() => onChange(f.key)}>{f.label}</button>
        ))}
      </div>
      <div className="select-field only-mobile">
        <label htmlFor={id}>Verdict</label>
        <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value as VerdictFilter)}>
          {VERDICT_FILTERS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
        </select>
      </div>
    </>
  );
}
