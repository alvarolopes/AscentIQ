import React from 'react';
const duration = value => value == null ? 'Duração indisponível' : `${Math.floor(value/60)}h${String(value%60).padStart(2,'0')}`;
const day = value => value ? new Date(value+'T12:00:00').toLocaleDateString('pt-BR') : 'Sem registro';
export default function SleepContext({sleep}) {
  const summary = sleep?.summary || {};
  const latest = summary.latest_duration_daily;
  const scored = summary.latest_scored_daily;
  return <div className="notice"><b>Sono registrado no Garmin</b>
    <p>{latest ? `${duration(latest.duration_minutes)} · ${day(latest.date)}` : 'Sem duração de sono disponível.'}</p>
    <p className="small">{scored ? `Última pontuação: ${scored.score} · ${day(scored.date)}` : 'Sem pontuação de sono disponível.'}</p>
    {summary.last_7_days_average_duration_minutes != null && <p className="small">Média de duração: {duration(Math.round(summary.last_7_days_average_duration_minutes))} · {summary.last_7_days_duration_count} de 7 dias com duração registrada.</p>}
    <p className="small muted">Datas atribuídas pelo Garmin. Duração e pontuação são medidas distintas e não comprovam recuperação.</p>
  </div>;
}
