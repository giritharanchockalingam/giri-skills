import Link from "next/link";
import { countsSentence, type SkillCounts } from "@/lib/countsText";

/** The one sentence that states skill counts (see lib/counts.ts and the Glossary). */
export function SkillCountsLine({ c }: { c: SkillCounts }) {
  return <p className="caption counts-line">{countsSentence(c)} · <Link className="link" href="/glossary#skill">what these mean</Link></p>;
}
