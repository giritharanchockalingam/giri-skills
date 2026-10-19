import { redirect } from "next/navigation";

/** Old link: the workspace's skills are in the publish pipeline. */
export default function WorkspacePage() { redirect("/pipeline"); }
