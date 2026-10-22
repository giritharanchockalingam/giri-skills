// Fictional fixture (tech-debt-audit-runner evals): the reports route — imports a sibling route's helper (TD4).
import { summarise } from "../dashboard/helpers";
import { ReportGrid, type Row } from "@/components/legacy/ReportGrid";
import { trackView } from "@/lib/analytics";
import { buildQuote, type Quote } from "@/server/services/quote-service";

export default async function ReportsPage() {
  trackView("reports");
  const quote: Quote = buildQuote([1200, 800], "USD");
  const summary = summarise([quote.total]);
  return (
    <main>
      <ReportGrid rows={[{ id: "q-1", label: "Quote", value: summary.total } satisfies Row]} />
    </main>
  );
}
