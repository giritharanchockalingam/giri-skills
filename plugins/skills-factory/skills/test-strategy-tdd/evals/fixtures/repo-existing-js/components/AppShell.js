"use client";
// FICTIONAL example client component (JSX in a .js file).
export default function AppShell({ title, children }) {
  return (
    <main>
      <h1>{title}</h1>
      {children}
    </main>
  );
}
