'use client';

import React, { useDeferredValue, useState } from 'react';
import {
  Chart,
  Card,
  Panel,
  Empty,
  formatNumber as fmt,
  formatDay as date,
} from '@/components/shared/charts';
import { PagedList } from '@/components/shared/ui';
import { ActivityFilters } from './shared';
import { daysBefore, weeklyStrength } from './utils';

export default function Strength({ data }) {
  const [from, setFrom] = useState(daysBefore(data.as_of, 90)),
    [to, setTo] = useState(data.as_of),
    [search, setSearch] = useState('');
  const query = useDeferredValue(search.toLowerCase());
  const rows = (data.strength || []).filter(
    (row) =>
      row.date >= from &&
      row.date <= to &&
      `${row.title} ${row.exercises.map((exercise) => exercise.name).join(' ')}`
        .toLowerCase()
        .includes(query),
  );
  const sum = (key) => rows.reduce((acc, row) => acc + (row[key] || 0), 0);
  return (
    <div className="space-y-5">
      <ActivityFilters {...{ from, to, setFrom, setTo, search, setSearch }} />
      <div className="grid gap-5 sm:grid-cols-3">
        <Card
          label="Sessões de força"
          value={rows.length}
          note="Cada sessão consolidada conta uma vez"
        />
        <Card
          label="Séries de trabalho"
          value={sum('working_sets')}
          note="Aquecimentos excluídos quando identificados"
        />
        <Card
          label="Volume registrado"
          value={fmt(sum('volume_kg'), 0)}
          unit="kg·rep"
          note="Total Hevy; inclui exercícios fora do gráfico"
        />
      </div>
      <Panel
        title="Volume semanal de força"
        sub="Carga × repetições nas séries de trabalho, separada por grupo. Core, séries sem carga e sessões sem detalhe Hevy não entram nas linhas."
      >
        <Chart
          rows={weeklyStrength(rows)}
          keys={[
            { key: 'legs', label: 'Pernas / kg·rep', color: '#3fb950' },
            { key: 'upper', label: 'Superiores / kg·rep', color: '#f78166' },
          ]}
          title="Volume semanal de pernas e superiores"
        />
      </Panel>
      <Panel
        title="Diário de musculação"
        sub={`${rows.length} sessões no período · detalhes completos por exercício`}
      >
        <PagedList
          items={rows}
          resetKey={from + to + query}
          label="sessões de força"
          empty={<Empty />}
        >
          {(page) =>
            page.map((session, index) => (
              <details className="session" key={session.id + '-' + index}>
                <summary>
                  <div>
                    <strong>{session.title}</strong>
                    <span>
                      {date(session.date)} · {session.duration || 'Sem duração'} ·{' '}
                      {session.avg_hr != null ? `${session.avg_hr} bpm média · ` : ''}
                      {session.max_hr != null ? `${session.max_hr} bpm máx · ` : ''}
                      {session.match_status === 'matched'
                        ? 'Garmin + Hevy'
                        : session.exercises.length
                          ? 'Hevy'
                          : 'Garmin / sem séries'}
                    </span>
                  </div>
                  <div className="session-stats">
                    {fmt(session.volume_kg, 0)} <small>kg·rep</small>
                    <b>
                      {session.working_sets == null ? 'Sem dado' : session.working_sets + ' séries'}
                    </b>
                  </div>
                </summary>
                <PagedList
                  items={session.exercises}
                  label="exercícios"
                  empty={
                    <Empty>
                      Esta sessão tem contexto Garmin, mas não há séries correspondentes do Hevy.
                    </Empty>
                  }
                >
                  {(exercises) =>
                    exercises.map((exercise, exerciseIndex) => (
                      <div className="exercise" key={exerciseIndex}>
                        <h3>{exercise.name}</h3>
                        <PagedList
                          items={exercise.sets.map((set, setIndex) => ({
                            ...set,
                            number: setIndex + 1,
                          }))}
                          label="séries"
                        >
                          {(sets) => (
                            <div
                              className="table-scroll"
                              tabIndex={0}
                              role="region"
                              aria-label="Registros em tabela"
                            >
                              <table>
                                <thead>
                                  <tr>
                                    <th>Série</th>
                                    <th>Tipo</th>
                                    <th>Carga / kg</th>
                                    <th>Repetições</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {sets.map((set) => (
                                    <tr key={set.number}>
                                      <td>{set.number}</td>
                                      <td>
                                        {set.set_type === 'warmup'
                                          ? 'Aquecimento'
                                          : set.set_type === 'normal'
                                            ? 'Trabalho'
                                            : set.set_type}
                                      </td>
                                      <td>{fmt(set.weight_kg)}</td>
                                      <td>{set.reps ?? 'Sem dado'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </PagedList>
                      </div>
                    ))
                  }
                </PagedList>
              </details>
            ))
          }
        </PagedList>
      </Panel>
    </div>
  );
}
