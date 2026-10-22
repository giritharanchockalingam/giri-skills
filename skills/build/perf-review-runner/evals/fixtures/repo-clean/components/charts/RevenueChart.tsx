"use client";
// fictional fixture — chart component; the heavy import is fine here (not a page) (perf-review-runner evals)
import { LineChart, Line } from "recharts";

export default function RevenueChart() {
  const data = [{ m: "Jan", v: 12 }, { m: "Feb", v: 19 }];
  return (
    <LineChart width={320} height={160} data={data}>
      <Line dataKey="v" />
    </LineChart>
  );
}
