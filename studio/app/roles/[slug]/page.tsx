import { TalentDetail } from "@/components/factory/TalentDetail";

export const dynamic = "force-dynamic";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: `${slug} · Roles` }; }

export default async function RolePage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ v?: string }> }) {
  const [{ slug }, { v }] = await Promise.all([params, searchParams]);
  return <TalentDetail kind="role" slug={slug} v={v} />;
}
