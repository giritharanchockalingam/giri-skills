import { redirect } from "next/navigation";

/** The overview was the factory's internals; the front door is now the home page. */
export default function OverviewPage() { redirect("/"); }
