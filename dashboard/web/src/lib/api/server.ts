import 'server-only';
import { cookies } from 'next/headers';
import { sessionSchema } from './contracts';

export async function getSession() {
  const session = (await cookies()).get('ascentiq_session');
  if (!session) return null;
  try {
    const response = await fetch(
      `${process.env.BACKEND_INTERNAL_URL ?? process.env.DEV_API_URL ?? 'http://api:8788'}/api/auth/session`,
      {
        headers: { Cookie: `ascentiq_session=${session.value}` },
        cache: 'no-store',
        signal: AbortSignal.timeout(5000),
      },
    );
    if (!response.ok) return null;
    return sessionSchema.parse(await response.json());
  } catch {
    return null;
  }
}
