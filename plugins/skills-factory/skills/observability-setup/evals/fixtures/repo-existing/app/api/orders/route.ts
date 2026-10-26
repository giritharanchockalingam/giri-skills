// FICTIONAL example code for evals: an existing route that still logs with console.*.
export async function GET(request: Request) {
  console.log("orders list requested", request.url);
  try {
    return Response.json({ orders: [] });
  } catch (err) {
    console.error("orders list failed", err);
    return new Response("error", { status: 500 });
  }
}
