'use client';

import React, { useId, useState } from 'react';
import {
  Card as Surface,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export const formatNumber = (value, digits = 1) =>
  value == null
    ? 'Sem dado'
    : Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });
export const formatDay = (value) =>
  value
    ? new Date(value.slice(0, 10) + 'T12:00:00Z').toLocaleDateString('pt-BR', { timeZone: 'UTC' })
    : 'Sem registro';

const colors = {
  fitness: '#3fb950',
  fatigue: '#f78166',
  form: '#d29922',
  volume: '#3fb950',
  km: '#3fb950',
};
const historicalColors = { '#16695e': '#3fb950', '#bd633e': '#f78166', '#a88926': '#d29922' };
const tones = { green: 'text-emerald-400', rust: 'text-orange-300', gold: 'text-amber-300' };

export function Card({ label, value, unit = null, note = '', tone = '' }) {
  return (
    <Surface className="min-w-0 gap-3 p-5">
      <CardHeader className="p-0">
        <CardDescription className="text-xs font-medium tracking-wide">{label}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 p-0">
        <div
          className={`flex flex-wrap items-baseline gap-2 text-3xl font-semibold tabular-nums ${tones[tone] || ''}`}
        >
          {value}
          {unit && <span className="text-sm font-normal text-muted-foreground">{unit}</span>}
        </div>
        {note && <p className="text-xs leading-relaxed text-muted-foreground">{note}</p>}
      </CardContent>
    </Surface>
  );
}

export function Panel({ title, sub, children, aside, className = '' }) {
  return (
    <Surface className={`min-w-0 gap-5 p-5 ${className}`}>
      <CardHeader className="flex flex-col gap-3 p-0 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <CardTitle className="text-lg leading-snug">
            <h2>{title}</h2>
          </CardTitle>
          {sub && <CardDescription className="leading-relaxed">{sub}</CardDescription>}
        </div>
        {aside}
      </CardHeader>
      <CardContent className="min-w-0 space-y-4 p-0">{children}</CardContent>
    </Surface>
  );
}

export function Empty({ children = 'Nenhum registro nesse período.' }) {
  return (
    <p className="rounded-lg border border-dashed border-border px-5 py-8 text-center text-sm text-muted-foreground">
      {children}
    </p>
  );
}

// SVG preserves the existing temporal scale and real gaps in the measured series.
// Its dynamic values are geometry/color attributes, not a runtime style engine.
export function Chart({
  rows = [],
  keys: inputKeys = [],
  height = 290,
  numbers = false,
  points = false,
  zeroBaseline = !inputKeys.some((key) => ['weight_kg', 'waist_cm'].includes(key.key)),
  title = 'Evolução dos dados',
}) {
  const [selectedKey, setSelectedKey] = useState(null);
  const descriptionId = useId();
  const keys = inputKeys.map((key) => ({
    ...key,
    color: historicalColors[key.color] || key.color || colors[key.key] || '#58a6ff',
  }));
  const occurrences = new Map();
  const rowKeys = rows.map((row) => {
    const occurrence = occurrences.get(row.date) || 0;
    occurrences.set(row.date, occurrence + 1);
    return row.id || `${row.date}:${occurrence}`;
  });
  const hover = selectedKey == null ? -1 : rowKeys.indexOf(selectedKey);
  const values = rows.flatMap((row) =>
    keys
      .map((key) => row[key.key])
      .filter((value) => value != null)
      .map(Number),
  );
  if (!rows.length || !values.length) return <Empty />;

  const width = 1000,
    left = 45,
    right = 18,
    top = 22,
    bottom = 38;
  const rawMin = Math.min(...values),
    rawMax = Math.max(...values);
  const padding = zeroBaseline
    ? 0
    : Math.max((rawMax - rawMin) * 0.15, Math.abs(rawMax) * 0.002, 0.05);
  const min = zeroBaseline ? Math.min(0, rawMin) : rawMin - padding;
  const max = zeroBaseline ? Math.max(1, rawMax) : rawMax + padding;
  const span = max - min || 1;
  const timestamps = rows.map((row) => Date.parse(row.date));
  const firstDate = Math.min(...timestamps),
    dateSpan = Math.max(...timestamps) - firstDate;
  const x = (index) =>
    left + (dateSpan ? (timestamps[index] - firstDate) / dateSpan : 0.5) * (width - left - right);
  const y = (value) => height - bottom - ((value - min) / span) * (height - top - bottom);

  function select(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const pointer = ((event.clientX - bounds.left) / bounds.width) * width;
    let nearest = 0;
    rows.forEach((row, index) => {
      if (Math.abs(x(index) - pointer) < Math.abs(x(nearest) - pointer)) nearest = index;
    });
    setSelectedKey(rowKeys[nearest]);
  }
  function navigate(event) {
    const current = Math.max(0, hover);
    const requested = {
      ArrowLeft: current - 1,
      ArrowRight: current + 1,
      Home: 0,
      End: rows.length - 1,
    }[event.key];
    if (requested == null) return;
    event.preventDefault();
    setSelectedKey(rowKeys[Math.max(0, Math.min(rows.length - 1, requested))]);
  }
  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
        {keys.map((key) => (
          <span className="inline-flex items-center gap-2" key={key.key}>
            <svg width="10" height="10" aria-hidden="true">
              <circle cx="5" cy="5" r="5" fill={key.color} />
            </svg>
            {key.label}
          </span>
        ))}
      </div>
      <svg
        className="block w-full rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
        role="img"
        aria-label={title}
        aria-describedby={descriptionId}
        tabIndex={0}
        viewBox={`0 0 ${width} ${height}`}
        onPointerMove={select}
        onPointerDown={select}
        onPointerLeave={(event) => {
          if (event.pointerType !== 'touch' && document.activeElement !== event.currentTarget)
            setSelectedKey(null);
        }}
        onFocus={() => setSelectedKey((previous) => previous || rowKeys[0])}
        onBlur={() => setSelectedKey(null)}
        onKeyDown={navigate}
      >
        <desc id={descriptionId}>
          Séries por data. Lacunas indicam dados ausentes. Use as setas esquerda e direita, Home ou
          End para consultar valores.
        </desc>
        {Array.from({ length: 5 }, (_, index) => {
          const value = min + (span * index) / 4;
          return (
            <g key={index}>
              <line
                x1={left}
                x2={width - right}
                y1={y(value)}
                y2={y(value)}
                className="stroke-border"
                strokeDasharray="4 5"
              />
              <text x="3" y={y(value) + 4} className="fill-muted-foreground text-[11px]">
                {formatNumber(value, span < 5 ? 2 : span < 20 ? 1 : 0)}
              </text>
            </g>
          );
        })}
        {keys.map((key) => {
          const chunks = [];
          let current = [];
          rows.forEach((row, index) => {
            if (row[key.key] != null) current.push([index, row[key.key]]);
            else if (current.length) {
              chunks.push(current);
              current = [];
            }
          });
          if (current.length) chunks.push(current);
          return (
            <g key={key.key}>
              {chunks.map((chunk, index) => (
                <polyline
                  key={index}
                  points={chunk.map(([idx, value]) => `${x(idx)},${y(value)}`).join(' ')}
                  fill="none"
                  stroke={key.color}
                  strokeWidth="2.7"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ))}
              {(points || rows.length <= 25) &&
                rows.map(
                  (row, index) =>
                    row[key.key] != null && (
                      <g key={rowKeys[index]}>
                        <circle cx={x(index)} cy={y(row[key.key])} r="3.4" fill={key.color} />
                        {numbers && (
                          <text
                            x={x(index)}
                            y={y(row[key.key]) - 9}
                            textAnchor="middle"
                            fill={key.color}
                            fontSize="11"
                          >
                            {formatNumber(row[key.key])}
                          </text>
                        )}
                      </g>
                    ),
                )}
            </g>
          );
        })}
        {[...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])].map((index) => (
          <text
            key={index}
            x={x(index)}
            y={height - 9}
            textAnchor={index === 0 ? 'start' : index === rows.length - 1 ? 'end' : 'middle'}
            className="fill-muted-foreground text-[11px]"
          >
            {formatDay(rows[index].date)}
          </text>
        ))}
        {hover >= 0 && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={top}
              y2={height - bottom}
              className="stroke-muted-foreground"
              opacity=".4"
            />
            {keys.map(
              (key) =>
                rows[hover][key.key] != null && (
                  <circle
                    key={key.key}
                    cx={x(hover)}
                    cy={y(rows[hover][key.key])}
                    r="5"
                    fill={key.color}
                    stroke="var(--card)"
                    strokeWidth="2"
                  />
                ),
            )}
          </g>
        )}
      </svg>
      <div
        className="flex min-h-10 flex-wrap items-center gap-x-5 gap-y-1 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground tabular-nums"
        aria-live="polite"
      >
        {hover >= 0 ? (
          <>
            <strong className="text-foreground">{formatDay(rows[hover].date)}</strong>
            {keys.map((key) => (
              <span key={key.key}>
                {key.label}:{' '}
                <strong className="text-foreground">{formatNumber(rows[hover][key.key])}</strong>
              </span>
            ))}
          </>
        ) : (
          'Passe sobre o gráfico, toque ou use o teclado para consultar os valores por dia.'
        )}
      </div>
    </div>
  );
}
