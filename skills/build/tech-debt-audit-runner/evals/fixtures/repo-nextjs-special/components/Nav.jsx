import Link from "next/link";

export function Nav() {
  return (
    <nav>
      <Link href="/">Home</Link>
      <Link href="/blog/hello">Blog</Link>
    </nav>
  );
}
