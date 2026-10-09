import SignIn from '@/features/auth/sign-in';
import { getSession } from '@/lib/api/server';
import { redirect } from 'next/navigation';

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string }>;
}) {
  if (await getSession()) redirect('/');
  const { returnTo = '/' } = await searchParams;
  return <SignIn returnTo={returnTo} />;
}
