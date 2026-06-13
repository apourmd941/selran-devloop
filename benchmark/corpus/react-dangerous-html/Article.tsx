// Fixture: XSS via dangerouslySetInnerHTML (seeded) + literal control.
export function Article({ body }: { body: string }) {
  // SEEDED BUG [RXSS-1]: remote/user content rendered as raw HTML.
  return <div dangerouslySetInnerHTML={{ __html: body }} />;
}

export function Footer() {
  // CLEAN CONTROL: literal string — must NOT be flagged.
  return <div dangerouslySetInnerHTML={{ __html: "&copy; 2026 Selran" }} />;
}
