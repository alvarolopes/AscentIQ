'use client';

import Nutrition from '@/features/nutrition/FoodDiary';
import { usePlatform } from '@/providers/platform-provider';

export default function Page() {
  const { selectedDay } = usePlatform();
  return <Nutrition initialDay={selectedDay} />;
}
