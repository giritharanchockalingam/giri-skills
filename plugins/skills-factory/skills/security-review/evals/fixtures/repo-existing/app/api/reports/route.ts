// fictional fixture — existing route handler in the repo the change lands in (security-review evals)
import { requireUser } from "@/lib/auth";
import { listReports } from "@/lib/db/reports";

export async function GET() {
  const user = await requireUser();
  return Response.json(await listReports(user.tenantId));
}
