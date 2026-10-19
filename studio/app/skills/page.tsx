import { redirect } from "next/navigation";

/** /skills alone has no page: workspace skills live in the publish pipeline. */
export default function SkillsIndex() { redirect("/pipeline"); }
