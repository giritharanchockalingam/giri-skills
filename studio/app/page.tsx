import { catalogRows, DOMAINS, VERDICTS } from "@/lib/data";
import { CatalogTable } from "@/components/CatalogTable";

export default function CatalogPage() {
  return (
    <>
      <h1 className="mb-2">Skills catalog</h1>
      <CatalogTable rows={catalogRows()} domains={DOMAINS} verdicts={VERDICTS} />
    </>
  );
}
