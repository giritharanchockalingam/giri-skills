export async function generateStaticParams() {
  return [{ slug: "hello" }];
}

export async function generateMetadata({ params }) {
  return { title: params.slug };
}

export default function Post({ params }) {
  return <article>{params.slug}</article>;
}
