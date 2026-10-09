'use client';

import React from 'react';
import { PagedList } from '@/components/shared/ui';
import { Empty, formatNumber as fmt, formatDay as date } from '@/components/shared/charts';
import { Input } from '@/components/ui/input';
import { activityKinds } from './utils';

export function ActivityTable({ rows, resetKey = '' }) {
  return (
    <PagedList items={rows} resetKey={resetKey} label="atividades" empty={<Empty />}>
      {(page) => (
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Registros em tabela">
          <table>
            <thead>
              <tr>
                <th>Data / atividade</th>
                <th>Modalidade</th>
                <th>Distância</th>
                <th>Tempo</th>
                <th>FC média</th>
                <th>D+</th>
              </tr>
            </thead>
            <tbody>
              {page.map((row, index) => (
                <tr key={row.id + '-' + index}>
                  <td>
                    <strong>{row.name}</strong>
                    <span className="small muted block">{date(row.date)}</span>
                  </td>
                  <td>
                    <span className="tag">{activityKinds[row.kind] || row.kind}</span>
                  </td>
                  <td>{row.distance_km != null ? fmt(row.distance_km, 2) + ' km' : 'Sem dado'}</td>
                  <td>{row.elapsed_time || 'Sem dado'}</td>
                  <td>{row.avg_hr == null ? 'Sem dado' : row.avg_hr + ' bpm'}</td>
                  <td>
                    {row.elevation_gain_m == null
                      ? 'Sem dado'
                      : fmt(row.elevation_gain_m, 0) + ' m'}
                    {row.elevation_source === 'official' && (
                      <span className="small muted block">Oficial</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PagedList>
  );
}

export function ActivityFilters({ from, to, setFrom, setTo, search, setSearch }) {
  return (
    <div className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)]">
      <label className="space-y-2 text-sm">
        De
        <Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
      </label>
      <label className="space-y-2 text-sm">
        Até
        <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
      </label>
      <label className="space-y-2 text-sm">
        Buscar
        <Input
          type="search"
          value={search}
          placeholder="Nome da atividade ou exercício"
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
    </div>
  );
}
