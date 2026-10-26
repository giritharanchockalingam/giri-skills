// Fictional fixture (tech-debt-audit-runner evals): lib/ reaching up into components/ (TD4) and untested (TD8).
import { Chart } from "@/components/Chart";

export function trackView(route: string): void {
  void Chart;
  console.info("view", route);
}
