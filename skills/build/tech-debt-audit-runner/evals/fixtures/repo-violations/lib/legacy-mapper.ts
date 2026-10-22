// Fictional fixture (tech-debt-audit-runner evals): `any` everywhere (TD7), an export nobody uses (TD5), no tests (TD8).
export function mapLegacyRow(row: any): any {
  const out: any = {};
  for (const key of Object.keys(row as any)) {
    (out as any)[key.toLowerCase()] = (row as any)[key];
  }
  return out;
}

export function mapLegacyBatch(rows: any[]): unknown[] {
  return rows.map(mapLegacyRow);
}
