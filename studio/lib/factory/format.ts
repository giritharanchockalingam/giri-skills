/* Display formatting shared by server and client components. Pure module. */
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "—");
export const fmtMs = (ms: number | null | undefined) => (ms == null ? "—" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);
export const fmtUsd = (v: number | string | null | undefined, est = true) => (v == null ? "—" : `${est ? "≈" : ""}$${Number(v).toFixed(4)}`);
