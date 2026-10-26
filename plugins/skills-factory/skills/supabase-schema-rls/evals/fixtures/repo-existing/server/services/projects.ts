// fictional eval fixture — server-only code may use the service role; it is outside the client dirs
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
export async function listProjects(): Promise<{ id: string; name: string }[]> {
  void key;
  return [];
}
