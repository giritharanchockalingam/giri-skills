import { upstream, upstreamSummary, UPSTREAM_CATEGORIES } from "@/lib/data";
import { UpstreamTable } from "@/components/UpstreamTable";
import { PageHead } from "@/components/PageHead";

export const metadata = { title: "Reference skills · Skills Factory" };

export default function UpstreamPage() {
  const s = upstreamSummary();
  const fetched = [...new Set(upstream.map((u) => u.fetched).filter(Boolean))].sort().at(-1);
  return (
    <>
      <PageHead
        eyebrow="Build · Reference skills"
        title="Fifty skills,"
        em="borrowed"
        lead={<>The {s.total} most-installed public skills, vendored at pinned commits — {s.vendor} from vendor teams, {s.community} community; {s.oss} open-source, {s.sourceAvailable} Anthropic source-available.</>}
        caption={<>Ranked by skills.sh installs · copied unchanged from the original repositories on {fetched ?? "—"}</>}
      />
      <UpstreamTable rows={upstream} categories={UPSTREAM_CATEGORIES} />
    </>
  );
}
