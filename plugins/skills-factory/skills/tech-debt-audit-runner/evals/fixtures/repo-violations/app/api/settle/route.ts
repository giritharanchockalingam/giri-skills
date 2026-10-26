// Fictional fixture (tech-debt-audit-runner evals): a route handler — its POST export is a framework contract, not dead code.
import { settle } from "@/server/services/invoice-service";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const { id } = (await req.json()) as { id: string };
  const charged = await settle(id);
  return Response.json({ charged });
}
