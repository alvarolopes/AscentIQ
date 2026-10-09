'use client';

import Running from '@/features/workouts/Running';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const { data } = usePlatform();
  return data ? <Running data={data} /> : null;
}
