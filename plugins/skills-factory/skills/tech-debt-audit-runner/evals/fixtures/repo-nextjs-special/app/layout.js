import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata = { title: "Special files", description: "Fixture" };
export const viewport = { themeColor: "#0a749f" };

export default function RootLayout({ children, modal }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        {children}
        {modal}
      </body>
    </html>
  );
}
