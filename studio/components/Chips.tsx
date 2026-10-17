"use client";

export function Chips<T extends string>({ label, options, value, onChange }: {
  label: string; options: readonly T[]; value: Set<T>; onChange: (next: Set<T>) => void;
}) {
  const toggle = (o: T) => {
    const next = new Set(value);
    if (next.has(o)) next.delete(o); else next.add(o);
    onChange(next);
  };
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={label}>
      <span className="mr-1 text-[11.5px] text-fg-3">{label}</span>
      {options.map((o) => (
        <button key={o} type="button" className="chip" aria-pressed={value.has(o)} onClick={() => toggle(o)}>{o}</button>
      ))}
      {value.size > 0 && (
        <button type="button" className="chip" onClick={() => onChange(new Set())} aria-label={`clear ${label}`}>×</button>
      )}
    </div>
  );
}
