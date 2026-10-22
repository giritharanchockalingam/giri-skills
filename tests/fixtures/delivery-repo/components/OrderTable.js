export function OrderTable({ orders }) {
  if (!orders || orders.length === 0) {
    return <p role="status">No orders yet.</p>;
  }
  return (
    <table>
      <thead>
        <tr><th scope="col">Order</th><th scope="col">Customer</th><th scope="col">Total</th></tr>
      </thead>
      <tbody>
        {orders.map((o) => (
          <tr key={o.id}><td>{o.id}</td><td>{o.customer}</td><td>{o.total.toFixed(2)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}
