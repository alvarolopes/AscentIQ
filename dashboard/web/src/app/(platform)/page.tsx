'use client';

import Dashboard from '@/features/dashboard/Dashboard';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const platform = usePlatform();
  return platform.data ? (
    <Dashboard
      data={platform.data}
      initialDay={platform.selectedDay}
      onNavigate={platform.navigate}
      onAssistant={platform.openAssistant}
    />
  ) : null;
}
