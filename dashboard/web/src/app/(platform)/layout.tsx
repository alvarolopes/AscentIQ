import { redirect } from 'next/navigation';
import { getSession } from '@/lib/api/server';
import { calendarDay } from '@/lib/dates';
import QueryProvider from '@/providers/query-provider';
import { PlatformProvider } from '@/providers/platform-provider';
import PlatformShell from '@/components/shell/platform-shell';
import { TooltipProvider } from '@/components/ui/tooltip';

export default async function Layout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session) redirect('/login');
  return (
    <QueryProvider>
      <TooltipProvider>
        <PlatformProvider initialDay={calendarDay()}>
          <PlatformShell username={session.username}>{children}</PlatformShell>
        </PlatformProvider>
      </TooltipProvider>
    </QueryProvider>
  );
}
