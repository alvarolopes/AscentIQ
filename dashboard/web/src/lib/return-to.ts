export function safeReturnTo(value: string, origin: string): string {
  try {
    if (!value.startsWith('/')) return '/';
    const destination = new URL(value, origin);
    if (destination.origin !== new URL(origin).origin) return '/';
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return '/';
  }
}
