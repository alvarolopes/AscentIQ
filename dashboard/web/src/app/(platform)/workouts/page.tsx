'use client';

import Overview from '@/features/workouts/Overview';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const { data } = usePlatform();
  return data ? <Overview data={data} /> : null;
}
