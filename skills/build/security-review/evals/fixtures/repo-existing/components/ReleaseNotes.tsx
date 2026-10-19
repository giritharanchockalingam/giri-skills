// fictional fixture — existing component that renders CMS HTML (medium: needs sanitising)
export function ReleaseNotes({ html }: { html: string }) {
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
