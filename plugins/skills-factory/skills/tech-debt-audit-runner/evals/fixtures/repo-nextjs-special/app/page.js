import { formatDate } from "@/lib/format";

export const dynamic = "force-static";
export const revalidate = 3600;

export default function Home() {
  return <main>Built {formatDate("2026-01-01T00:00:00Z")}</main>;
}
