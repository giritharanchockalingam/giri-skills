import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { AssistantChat } from "@/components/assistant/AssistantChat";
import { llmConfig } from "@/lib/assistant/llm";

export const metadata = { title: "Assistant · Skills Factory" };
export const dynamic = "force-dynamic";

const STARTERS = [
  "Which repositories are failing a scorecard check?",
  "What did the pull-request gate find on the latest PR?",
  "Who owns each repository, and what stack does it use?",
  "Which skill fits a data protection impact assessment?",
  "How many hours did skills save in the last 30 days?",
];

/** Ask the workspace: answers come only from its own records, with the evidence shown. */
export default async function AssistantPage() {
  await requireWorkspace();
  const llm = llmConfig();
  return (
    <>
      <PageHead eyebrow="Assistant" title="Ask your" em="workspace" after="."
        lead="Questions about your repositories, scorecards, automations, usage and skills — answered from this workspace's own records, with the lookups behind every answer. Read-only." />
      <section className="card card-pad">
        {llm.ok ? <AssistantChat starters={STARTERS} /> : <p className="caption ink-rust" role="status">{llm.reason}</p>}
      </section>
    </>
  );
}
