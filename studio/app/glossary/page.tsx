import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { GLOSSARY } from "@/lib/nav";

export const metadata = { title: "Glossary · Skills Factory" };

/** One name per concept — the words this portal uses, what each means, and the words it does not use for it. */
export default function GlossaryPage() {
  return (
    <>
      <PageHead eyebrow="Admin · glossary" title="One name per" em="concept" after="."
        lead="Every page uses these words, and only these. Older names that still appear in addresses or code are listed so they can be recognised, not used." />
      <div className="card"><div className="tablewrap"><table className="mini cat-table">
        <thead><tr><th>Term</th><th>Means</th><th>Not called</th></tr></thead>
        <tbody>{GLOSSARY.map((g) => (
          <tr key={g.term} id={g.term.toLowerCase().replace(/\s+/g, "-")}>
            <td><Link className="link" href={g.where}><b>{g.term}</b></Link></td>
            <td>{g.means}</td>
            <td className="caption">{g.not.length ? g.not.join(", ") : "—"}</td>
          </tr>))}</tbody>
      </table></div></div>
    </>
  );
}
