"use client";

export default function Error({ error, reset }) {
  console.error(error);
  return (
    <div>
      <p>Something went wrong.</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
