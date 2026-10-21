"use client";
/* The finished deliverables of a run, ready to use: the document (opens printable, Save as PDF from there), each
 * diagram as a picture with SVG and PNG downloads, and the editable draw.io file. Rendering is safe for any skill's
 * output: SVG is shown as an image (never inline markup) and HTML in a sandbox with scripts disabled. */
import { useState } from "react";
import { deliverables, MIME, outputKind, svgDataUrl } from "@/lib/outputKind";

function save(name: string, content: string | Blob, type?: string) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: type ?? MIME[outputKind(name)] });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

/** SVG -> PNG at 2x in the browser (canvas); nothing leaves the page. */
async function savePng(name: string, svg: string) {
  const img = new Image();
  img.src = svgDataUrl(svg);
  await img.decode();
  const scale = 2, c = document.createElement("canvas");
  c.width = img.naturalWidth * scale; c.height = img.naturalHeight * scale;
  const g = c.getContext("2d")!;
  g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
  g.drawImage(img, 0, 0, c.width, c.height);
  const blob: Blob = await new Promise((ok) => c.toBlob((b) => ok(b!), "image/png"));
  save(name.replace(/\.svg$/i, ".png"), blob);
}

export function Deliverables({ files }: { files: Record<string, string | null | undefined> }) {
  const d = deliverables(Object.keys(files).filter((p) => files[p] != null));
  const [open, setOpen] = useState(false);
  if (!d.doc && !d.diagrams.length && !d.drawio) return null;
  const base = (p: string) => p.split("/").pop() || p;
  const openDoc = () => {
    const w = window.open("", "_blank");
    if (w) { w.document.open(); w.document.write(files[d.doc!] ?? ""); w.document.close(); }
  };
  return (
    <section className="deliverables">
      <div className="h3" style={{ margin: "0 0 6px" }}>Deliverables</div>
      {d.doc && (
        <div className="deliv-doc">
          <span><b>{base(d.doc)}</b> <span className="caption">— the whole document with its diagrams; open it and use Print → Save as PDF for a PDF</span></span>
          <span className="run-file-actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={openDoc}>Open document</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>{open ? "Hide preview" : "Preview here"}</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => save(base(d.doc!), files[d.doc!] ?? "")}>Download HTML</button>
          </span>
        </div>
      )}
      {open && d.doc && <iframe className="deliv-frame" title="Document preview" sandbox="" srcDoc={files[d.doc] ?? ""} />}
      {d.diagrams.length > 0 && (
        <div className="deliv-grid">
          {d.diagrams.map((p) => (
            <figure key={p} className="deliv-fig">
              <a href={svgDataUrl(files[p] ?? "")} target="_blank" rel="noreferrer" title="Open full size"><img src={svgDataUrl(files[p] ?? "")} alt={base(p)} /></a>
              <figcaption>
                <span>{base(p)}</span>
                <span className="run-file-actions">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => save(base(p), files[p] ?? "")}>SVG</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => savePng(base(p), files[p] ?? "")}>PNG</button>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      {d.drawio && (
        <div className="deliv-doc">
          <span><b>{base(d.drawio)}</b> <span className="caption">— every diagram, editable: open in diagrams.net (draw.io), Confluence or Visio import</span></span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => save(base(d.drawio!), files[d.drawio!] ?? "")}>Download draw.io</button>
        </div>
      )}
    </section>
  );
}
