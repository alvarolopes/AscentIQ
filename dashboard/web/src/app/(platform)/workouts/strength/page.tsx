'use client';

import Strength from '@/features/workouts/Strength';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const { data } = usePlatform();
  return data ? <Strength data={data} /> : null;
}
