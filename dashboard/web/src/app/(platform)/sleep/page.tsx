'use client';

import Sleep from '@/features/sleep/Sleep';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const { data } = usePlatform();
  return data ? <Sleep data={data} /> : null;
}
