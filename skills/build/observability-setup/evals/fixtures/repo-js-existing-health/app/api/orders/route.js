import { NextResponse } from "next/server";

export async function GET() {
  console.log("orders listed");
  return NextResponse.json({ orders: [] });
}
