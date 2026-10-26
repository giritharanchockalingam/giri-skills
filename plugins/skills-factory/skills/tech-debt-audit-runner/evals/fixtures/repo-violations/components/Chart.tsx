// Fictional fixture (tech-debt-audit-runner evals): a presentational chart.
export function Chart({ points }: { points: number[] }) {
  return <svg>{points.map((p, i) => <rect key={i} height={p} />)}</svg>;
}
