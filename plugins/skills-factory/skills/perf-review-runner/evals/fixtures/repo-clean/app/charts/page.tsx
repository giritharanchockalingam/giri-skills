// fictional fixture — charts page loads the chart library on the client only (perf-review-runner evals)
import dynamic from "next/dynamic";

const RevenueChart = dynamic(() => import("@/components/charts/RevenueChart"), { ssr: false });

export default function ChartsPage() {
  return <RevenueChart />;
}
