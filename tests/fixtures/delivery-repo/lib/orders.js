// Order queries: a fictional in-memory store so the fixture needs no database.
const ORDERS = [
  { id: "ord_1001", customer: "Alder & Co", total: 120.5, status: "paid" },
  { id: "ord_1002", customer: "Birch Ltd", total: 80.0, status: "open" },
];

export async function listOrders({ limit = 50 } = {}) {
  return ORDERS.slice(0, limit);
}
