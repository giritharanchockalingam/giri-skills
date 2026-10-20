export function esc(s: unknown): string;
export function inline(s: string): string;
/** Markdown → safe HTML (text escaped; only http(s)/mailto/relative links kept). */
export function mdToHtml(md: string): string;
export function flagBaselines(s: string): string;
