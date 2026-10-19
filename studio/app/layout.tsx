import type { Metadata } from "next";
import "./globals.css";
import { Suspense } from "react";
import { Nav } from "@/components/Nav";
import { SectionTabs } from "@/components/SectionTabs";

export const metadata: Metadata = {
  title: "Skills Factory · giri-skills",
  description: "Create, test, evaluate, approve, publish and run AI skills — with the giri-skills catalog, evals and upstream library.",
};

const FONTS =
  "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Public+Sans:wght@400;500;600&family=Roboto+Mono:wght@400;500&display=swap";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body>
        <Nav />
        <Suspense fallback={null}><SectionTabs /></Suspense>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
