"use client";

export default function GlobalError({ reset }) {
  return (
    <html>
      <body>
        <button onClick={reset}>Try again</button>
      </body>
    </html>
  );
}
