/* What an output file is, for showing and downloading it properly. Pure. */
export type OutputKind = "svg" | "html" | "drawio" | "md" | "csv" | "json" | "text";
export function outputKind(path: string): OutputKind {
  const p = path.toLowerCase();
  if (p.endsWith(".svg")) return "svg";
  if (p.endsWith(".html") || p.endsWith(".htm")) return "html";
  if (p.endsWith(".drawio")) return "drawio";
  if (p.endsWith(".md")) return "md";
  if (p.endsWith(".csv")) return "csv";
  if (p.endsWith(".json")) return "json";
  return "text";
}
export const MIME: Record<OutputKind, string> = {
  svg: "image/svg+xml", html: "text/html;charset=utf-8", drawio: "application/xml", md: "text/markdown;charset=utf-8",
  csv: "text/csv;charset=utf-8", json: "application/json", text: "text/plain;charset=utf-8",
};
/** SVG as an <img> source: images never run scripts, so a skill's SVG is shown safely. */
export const svgDataUrl = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
/** The deliverables worth a one-click download, in reading order: the document, then diagrams, then the editable file. */
export function deliverables(paths: string[]): { doc: string | null; diagrams: string[]; drawio: string | null } {
  return {
    doc: paths.find((p) => outputKind(p) === "html") ?? null,
    diagrams: paths.filter((p) => outputKind(p) === "svg").sort(),
    drawio: paths.find((p) => outputKind(p) === "drawio") ?? null,
  };
}
