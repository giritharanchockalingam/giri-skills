// Fictional fixture (ui-component-quality evals): async detail view in plain JavaScript — no loading state, raw HTML.
"use client";

import { useEffect, useState } from "react";

export default function OrderDetail({ orderId }) {
  const [order, setOrder] = useState(null);
  useEffect(() => {
    fetch(`/api/orders?id=${orderId}`).then((r) => r.json()).then(setOrder);
  }, [orderId]);
  return (
    <article style={{ width: 800 }}>
      <h2>Order {order?.number}</h2>
      <div dangerouslySetInnerHTML={{ __html: order?.notesHtml ?? "" }} />
    </article>
  );
}
