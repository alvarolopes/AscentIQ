'use client';

import React, { useState } from 'react';
import {
  Chart,
  Card,
  Panel,
  formatNumber as fmt,
  formatDay as date,
} from '@/components/shared/charts';
import { PagedList } from '@/components/shared/ui';
import { NativeSelect } from '@/components/ui/native-select';
import SleepContext from '@/features/sleep/SleepContext';
import { ActivityTable } from './shared';
import { activityKinds } from './utils';

export function Performance({ data }) {
  const [range, setRange] = useState('21'),
    [numbers, setNumbers] = useState(false);
  const series = data.performance?.series || [];
  const rows = range === 'all' ? series : series.slice(-Number(range));
  return (
    <Panel
      title="Carga, adaptação e equilíbrio"
      sub="Seu modelo de Fitness, Fadiga e Forma. Uma leitura de carga, não um diagnóstico."
      aside={
        <div className="flex flex-wrap items-center gap-3">
          <NativeSelect
            aria-label="Período do gráfico"
            value={range}
            onChange={(event) => setRange(event.target.value)}
          >
            <option value="21">3 semanas</option>
            <option value="90">90 dias</option>
            <option value="180">6 meses</option>
            <option value="all">Todo o histórico</option>
          </NativeSelect>
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={numbers}
              onChange={(event) => setNumbers(event.target.checked)}
            />
            Valores
          </label>
        </div>
      }
    >
      <Chart
        rows={rows}
        keys={[
          { key: 'fitness', label: 'Fitness' },
          { key: 'fatigue', label: 'Fadiga' },
          { key: 'form', label: 'Forma' },
        ]}
        numbers={numbers}
      />
      <details className="method">
        <summary>Como ler esses números</summary>
        <p>
          Fitness = carga crônica suavizada em 42 dias. Fadiga = carga aguda em 7 dias. Forma =
          Fitness menos Fadiga. A carga combina FC, duração, modalidade, D+ e componente muscular
          Hevy. Não é TSS oficial, VO₂max nem percentual de condicionamento.
        </p>
        <PagedList items={[...rows].reverse()} resetKey={range} label="carga diária">
          {(page) => (
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Registros em tabela"
            >
              <table>
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Fitness</th>
                    <th>Fadiga</th>
                    <th>Forma</th>
                    <th>Carga</th>
                  </tr>
                </thead>
                <tbody>
                  {page.map((row) => (
                    <tr key={row.date}>
                      <td>{date(row.date)}</td>
                      <td>{fmt(row.fitness)}</td>
                      <td>{fmt(row.fatigue)}</td>
                      <td>{fmt(row.form)}</td>
                      <td>{fmt(row.daily_load)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </PagedList>
      </details>
    </Panel>
  );
}

export default function Overview({ data }) {
  const summary = data.performance?.summary || {},
    week = data.week || {},
    body = data.body?.current || {};
  const goal = data.goals?.endurance,
    activities = data.activities || [],
    strength = data.strength || [];
  return (
    <div className="space-y-5">
      {goal?.status === 'active_goal' && (
        <section
          className="grid gap-2 rounded-xl border border-primary/25 bg-primary/5 p-5 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-5"
          aria-label="Objetivo esportivo atual"
        >
          <span className="text-xs font-medium tracking-wide text-primary">
            OBJETIVO ESPORTIVO ATUAL
          </span>
          <strong>
            {goal.name} · {fmt(goal.target_distance_km, 0)} km
          </strong>
          <span className="text-muted-foreground sm:col-start-2">
            {date(goal.event_date)} · Objetivo: completar bem, com endurance e gestão de esforço.
            Pace não é meta.
          </span>
        </section>
      )}
      <div className="grid gap-5 sm:grid-cols-3">
        <Card
          label="Fitness"
          value={fmt(summary.fitness)}
          note="Carga crônica · 42 dias"
          tone="green"
        />
        <Card label="Fadiga" value={fmt(summary.fatigue)} note="Carga aguda · 7 dias" tone="rust" />
        <Card
          label="Forma"
          value={(summary.form > 0 ? '+' : '') + fmt(summary.form)}
          note="Fitness − Fadiga · índice estimado"
          tone="gold"
        />
      </div>
      <Performance data={data} />
      <div className="grid min-w-0 gap-5 xl:grid-cols-2">
        <Panel
          title="Sua semana em movimento"
          sub={`${date(week.start)} a ${date(week.end)} · últimos 7 dias`}
        >
          <div className="grid grid-cols-2 gap-5 text-sm">
            {[
              [fmt(week.running_km, 2), 'km de corrida'],
              [week.strength_sessions ?? 'Sem dado', 'sessões de força'],
              [week.working_sets ?? 'Sem dado', 'séries de trabalho'],
              [fmt(week.running_elevation_m, 0), 'metros D+ corrida'],
            ].map(([value, label]) => (
              <div className="space-y-1" key={label}>
                <strong className="block text-2xl font-semibold tabular-nums">{value}</strong>
                <span className="text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
          <div className="space-y-3">
            {Object.entries(week.by_kind || {}).map(([kind, count]) => (
              <div
                className="grid grid-cols-[5rem_minmax(0,1fr)_auto] items-center gap-3 text-sm"
                key={kind}
              >
                <span>{activityKinds[kind] || kind}</span>
                <progress
                  className="h-2 w-full overflow-hidden rounded-full accent-primary"
                  value={count}
                  max={Math.max(1, week.activity_count || 0)}
                  aria-label={`${activityKinds[kind] || kind}: ${count} atividades`}
                />
                <strong className="tabular-nums">{count}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Corpo & recuperação" sub="Referências com data, sem inferir medidas atuais">
          <div className="space-y-2 rounded-lg border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              Avaliação corporal · {date(data.body?.reference_date)}
            </p>
            <p className="text-3xl font-semibold tabular-nums">
              {fmt(body.body_fat_pct, 2)}{' '}
              <span className="text-sm font-normal text-muted-foreground">% gordura</span>
            </p>
            <p className="text-sm text-muted-foreground">
              {fmt(body.weight_kg)} kg · {fmt(body.lean_mass_kg, 2)} kg de massa magra
            </p>
          </div>
          <SleepContext sleep={data.sleep} />
        </Panel>
      </div>
      <Panel
        title="Atividades mais recentes"
        sub="Garmin para o esforço cardiovascular. Hevy para séries e exercícios."
      >
        <ActivityTable rows={activities} />
      </Panel>
      <p className="text-xs text-muted-foreground">
        Base privada · {activities.length} atividades · {strength.length} sessões de força
        consolidadas · Sem LLM nos cálculos
      </p>
    </div>
  );
}
