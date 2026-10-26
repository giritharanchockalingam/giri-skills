// Fictional fixture (ui-component-quality evals): filter form with every control labelled.
"use client"; // reason: controlled form inputs

import type { ComponentProps } from "react";

type OrderFiltersProps = Pick<ComponentProps<"form">, "onSubmit"> & {
  statuses: string[];
};

const STATUS_HELP = ["Open", "Paid", "Overdue"];

export function OrderFilters({ statuses, onSubmit }: OrderFiltersProps) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 md:w-[720px]">
      <label>
        Customer name
        <input name="customer" type="text" />
      </label>
      <label htmlFor="status">Status</label>
      <select id="status" name="status">
        {statuses.length === 0 ? <option>All</option> : null}
        {statuses.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <textarea aria-label="Notes" name="notes" />
      <ul>
        {STATUS_HELP.map((h) => <li key={h}>{h}</li>)}
      </ul>
      <button type="submit">Apply filters</button>
    </form>
  );
}
