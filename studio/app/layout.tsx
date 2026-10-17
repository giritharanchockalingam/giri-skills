import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { meta } from "@/lib/data";

export const metadata: Metadata = {
  title: "giri-skills studio",
  description: "Skill catalog, eval scorecard and findings for the giri-skills repo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav meta={meta} />
        <main className="mx-auto max-w-[1400px] px-4 py-4">{children}</main>
      </body>
    </html>
  );
}
