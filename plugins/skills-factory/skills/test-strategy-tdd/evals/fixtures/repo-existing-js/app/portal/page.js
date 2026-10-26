// FICTIONAL example page (JavaScript + JSX, no TypeScript).
import AppShell from "@/components/AppShell";
import { pendingNudges } from "@/lib/coach";

export default async function PortalPage() {
  const nudges = await pendingNudges("demo-patient");
  return (
    <AppShell title="Your portal">
      <p>{nudges.length} coach nudge(s) waiting</p>
    </AppShell>
  );
}
