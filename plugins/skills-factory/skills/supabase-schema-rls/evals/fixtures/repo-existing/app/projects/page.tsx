// fictional eval fixture — client page that reads through the anon client only
import { listProjects } from "@/server/services/projects";
export default async function ProjectsPage() {
  const projects = await listProjects();
  return <ul>{projects.map((p) => <li key={p.id}>{p.name}</li>)}</ul>;
}
