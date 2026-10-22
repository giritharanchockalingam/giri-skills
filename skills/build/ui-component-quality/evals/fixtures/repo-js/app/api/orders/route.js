// Fictional fixture (ui-component-quality evals): an existing Route Handler — plain JavaScript, no JSX; must NOT be scanned.
import { NextResponse } from "next/server";
import { listOrders } from "../../../lib/orders";

export async function GET(request) {
  const id = new URL(request.url).searchParams.get("id");
  const orders = await listOrders();
  const hit = id ? orders.find((o) => o.id === id) : null;
  if (id && !hit) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(hit ?? orders);
}
