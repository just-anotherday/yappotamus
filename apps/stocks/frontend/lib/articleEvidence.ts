/** Match a publisher and its subdomains without accepting lookalike suffixes. */
export function isPublisherHost(hostname: string, domain: string): boolean {
  const host = hostname.toLowerCase();
  const publisher = domain.toLowerCase();
  return host === publisher || host.endsWith(`.${publisher}`);
}

export function articleLink(value?: string | null): { href: string; publisher: string } | null {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value.trim());
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
    return { href: url.href, publisher: url.hostname.replace(/^www\./, '') };
  } catch {
    return null;
  }
}
