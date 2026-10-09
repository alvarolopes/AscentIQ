'use client';

import React from 'react';
import { formatDay } from '@/components/shared/charts';
import { sleepDuration } from './sleepView';

export default function SleepContext({ sleep }) {
  const summary = sleep?.summary || {},
    latest = summary.latest_duration_daily,
    scored = summary.latest_scored_daily;
  return (
    <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-4 text-sm">
      <strong>Sono registrado no Garmin</strong>
      <p>
        {latest
          ? `${sleepDuration(latest.duration_minutes)} · ${formatDay(latest.date)}`
          : 'Sem duração de sono disponível.'}
      </p>
      <p className="text-xs">
        {scored
          ? `Última pontuação: ${scored.score} · ${formatDay(scored.date)}`
          : 'Sem pontuação de sono disponível.'}
      </p>
      {summary.last_7_days_average_duration_minutes != null && (
        <p className="text-xs">
          Média de duração:{' '}
          {sleepDuration(Math.round(summary.last_7_days_average_duration_minutes))} ·{' '}
          {summary.last_7_days_duration_count} de 7 dias com duração registrada.
        </p>
      )}
      <p className="text-xs leading-relaxed text-muted-foreground">
        Datas atribuídas pelo Garmin. Duração e pontuação são medidas distintas e não comprovam
        recuperação.
      </p>
    </div>
  );
}
