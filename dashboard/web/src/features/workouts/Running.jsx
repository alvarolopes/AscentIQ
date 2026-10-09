'use client';

import React, { useDeferredValue, useState } from 'react';
import {
  Chart,
  Card,
  Panel,
  formatNumber as fmt,
  formatDay as date,
} from '@/components/shared/charts';
import { PagedList } from '@/components/shared/ui';
import { ActivityFilters, ActivityTable } from './shared';
import { daysBefore, weeklyRunning } from './utils';

export default function Running({ data }) {
  const [from, setFrom] = useState(daysBefore(data.as_of, 90)),
    [to, setTo] = useState(data.as_of),
    [search, setSearch] = useState('');
  const query = useDeferredValue(search.toLowerCase());
  const rows = (data.activities || []).filter(
    (row) =>
      row.kind === 'running' &&
      row.date >= from &&
      row.date <= to &&
      row.name?.toLowerCase().includes(query),
  );
  const total = rows.reduce(
    (acc, row) => ({
      km: acc.km + (row.distance_km || 0),
      seconds: acc.seconds + (row.duration_seconds || 0),
      d: acc.d + (row.elevation_gain_m || 0),
    }),
    { km: 0, seconds: 0, d: 0 },
  );
  const races = data.race_index?.entries || [];
  return (
    <div className="space-y-5">
      <ActivityFilters {...{ from, to, setFrom, setTo, search, setSearch }} />
      <div className="grid gap-5 sm:grid-cols-3">
        <Card
          label="Distância no período"
          value={fmt(total.km, 2)}
          unit="km"
          note={`${rows.length} atividades`}
        />
        <Card
          label="Tempo em atividade"
          value={fmt(total.seconds / 3600)}
          unit="h"
          note="Duração total registrada"
        />
        <Card
          label="Subida acumulada"
          value={fmt(total.d, 0)}
          unit="m"
          note="GPX oficial quando vinculado; relógio nos demais"
        />
      </div>
      <Panel
        title="Volume semanal de corrida"
        sub="Distância registrada por semana; semanas sem registros não são interpoladas."
      >
        <Chart rows={weeklyRunning(rows)} keys={[{ key: 'km', label: 'km / semana' }]} />
      </Panel>
      <Panel title="Histórico de corridas">
        <ActivityTable rows={rows} resetKey={from + to + query} />
      </Panel>
      {races.length > 0 && (
        <Panel
          title="Execução nas provas / IEP-100"
          sub={`Benchmark histórico, não prontidão atual. Índice calculado em ${date(data.race_index.generated_at)}.`}
        >
          <Chart
            rows={races}
            keys={[{ key: 'performance_execution_index', label: 'IEP / 100', color: '#a88926' }]}
            numbers
          />
          <PagedList items={races} label="provas">
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
                      <th>Prova</th>
                      <th>Data</th>
                      <th>Tempo</th>
                      <th>IEP</th>
                      <th>Confiança</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.map((race, index) => (
                      <tr key={race.id || index}>
                        <td>{race.name}</td>
                        <td>{date(race.date)}</td>
                        <td>{race.elapsed_time}</td>
                        <td>{fmt(race.performance_execution_index)}</td>
                        <td>{race.confidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PagedList>
        </Panel>
      )}
    </div>
  );
}
