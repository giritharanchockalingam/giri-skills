import { TabBar } from "@/components/TabBar";

const views = [
  { seg: "", label: "Overview" }, { seg: "test", label: "Test" }, { seg: "authoring", label: "Instructions" },
  { seg: "evaluations", label: "Evaluations" }, { seg: "files", label: "Files" }, { seg: "activity", label: "Activity" },
  { seg: "release", label: "Release" },
];

/** The coherent views of one skill (sticky tab bar); the selected version (?v=) travels with the navigation. */
export function SkillSubNav({ slug }: { slug: string }) {
  return <TabBar base={`/skills/${slug}`} tabs={views} keep={["v"]} label="Skill views" />;
}
