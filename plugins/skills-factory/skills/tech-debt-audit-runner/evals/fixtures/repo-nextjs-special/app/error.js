"use client";

export default function Error({ error, reset }) {
  return (
    <div>
      <p>{error.message}</p>
      <button onClick={reset}>Retry</button>
    </div>
  );
}
