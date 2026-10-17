import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { meta } from "@/lib/data";

export const metadata: Metadata = {
  title: "giri-skills studio",
  description: "Skill catalog, eval scorecard and findings for the giri-skills repo",
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
        <Nav meta={meta} />
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
