// Fictional fixture (ui-component-quality evals): a plain .js utility — no JSX; must NOT be scanned even though it
// contains `<` comparisons, an `img` word and an HTML string with an unlabelled input.
const ORDERS = [
  { id: "o-1", number: "1001", customer: "Northwind Supply", total: 120, paid: true, notesHtml: "<p>Ship Tuesday</p>" },
  { id: "o-2", number: "1002", customer: "Contoso Traders", total: 80, paid: false, notesHtml: "" },
];

export async function listOrders() {
  return ORDERS.filter((o) => o.total < 1000 && o.total > 0);
}

export function receiptHtml(order) {
  const img = order.paid ? "/paid.png" : "/due.png";
  return `<div><img src="${img}"><input type="text" placeholder="note"></div>`;
}
