// Kept from the v1 portal; mapLegacy is still used by its test, oldHelper by nothing.
export function mapLegacy(row) {
  return { id: row.ID, name: row.NAME };
}

export function oldHelper(x) {
  return x * 2;
}
