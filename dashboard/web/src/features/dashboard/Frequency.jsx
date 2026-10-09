'use client';

import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { personalApi, dayLabel, format, today } from '@/lib/personalApi';
import { cn } from '@/lib/utils';

const levels = [
  'frequency-level-0',
  'frequency-level-1',
  'frequency-level-2',
  'frequency-level-3',
  'frequency-level-4',
];
const levelFor = (count) => Math.max(0, Math.min(4, Number(count) || 0));
const calendarYear = () => Number(today().slice(0, 4));
function subscribeCalendarYear(notify) {
  window.addEventListener('focus', notify);
  document.addEventListener('visibilitychange', notify);
  return () => {
    window.removeEventListener('focus', notify);
    document.removeEventListener('visibilitychange', notify);
  };
}

function DaySummary({ row }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div>
        <strong className="block">{dayLabel(row.date)}</strong>
        <span className="text-muted-foreground">{row.count} de 4 categorias</span>
      </div>
      {row.count === 0 ? (
        <p>Nenhum registro.</p>
      ) : (
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
          {row.sleep_minutes != null && (
            <>
              <dt>Sono</dt>
              <dd>{format(row.sleep_minutes / 60)} h</dd>
            </>
          )}
          {row.meal_count > 0 && (
            <>
              <dt>Alimentação</dt>
              <dd>
                {row.kcal != null ? `${format(row.kcal, 0)} kcal` : 'Estimativa pendente'}
                {row.pending_count > 0 && ` · ${row.pending_count} pendente(s)`}
              </dd>
            </>
          )}
          {row.running_count > 0 && (
            <>
              <dt>Corrida</dt>
              <dd>
                {row.running_km != null
                  ? `${format(row.running_km)} km`
                  : 'Distância não informada'}
              </dd>
            </>
          )}
          {row.strength_count > 0 && (
            <>
              <dt>Força</dt>
              <dd>{row.strength_count} sessão(ões)</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

export default function Frequency({ revision, initialYear }) {
  const currentYear = useSyncExternalStore(
    subscribeCalendarYear,
    calendarYear,
    () => initialYear ?? null,
  );
  const [selectedYear, setYear] = useState(initialYear ?? null);
  const year = selectedYear ?? currentYear;
  const [activeDate, setActiveDate] = useState(null);
  const [focusedDay, setFocusedDay] = useState(null);
  const root = useRef(null),
    previousRevision = useRef(revision);
  const tooltipId = useId(),
    queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['frequency', year],
    queryFn: ({ signal }) => personalApi(`frequency?year=${year}`, undefined, signal),
    enabled: year != null,
  });
  useEffect(() => {
    if (previousRevision.current !== revision && year != null) {
      previousRevision.current = revision;
      queryClient.invalidateQueries({ queryKey: ['frequency', year] });
    }
  }, [revision, year, queryClient]);
  const days = query.data?.year === year ? query.data.days : [];
  const ready = query.data?.year === year;
  const offset = days.length ? new Date(days[0].date + 'T12:00:00Z').getUTCDay() : 0;
  const weeks = Math.ceil((days.length + offset) / 7);
  const firstFocusable =
    days.find((row) => row.date === focusedDay)?.date ||
    days.find((row) => row.date === today())?.date ||
    days[0]?.date;

  function moveFocus(event, index) {
    const shifts = { ArrowDown: 1, ArrowUp: -1, ArrowRight: 7, ArrowLeft: -7 };
    if (!(event.key in shifts) && !['Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? days.length - 1
          : Math.max(0, Math.min(days.length - 1, index + shifts[event.key]));
    const next = days[nextIndex]?.date;
    if (next) {
      setFocusedDay(next);
      root.current?.querySelector(`[data-frequency-date="${next}"]`)?.focus();
    }
  }

  return (
    <section className="panel frequency" ref={root}>
      <div className="panel-heading">
        <div>
          <h2>Frequência dos registros</h2>
          <p>
            {ready
              ? `${format(
                  days.reduce((sum, row) => sum + row.count, 0),
                  0,
                )} pontos em ${days.filter((row) => row.count > 0).length} dias · ${year}`
              : 'Carregando registros…'}
          </p>
        </div>
        <Label className="flex-col items-start gap-2">
          Ano
          <NativeSelect
            aria-label="Ano da frequência"
            value={year ?? ''}
            disabled={currentYear == null}
            onChange={(event) => {
              setYear(Number(event.target.value));
              setActiveDate(null);
              setFocusedDay(null);
            }}
          >
            {currentYear == null ? (
              <option value="">Carregando…</option>
            ) : (
              Array.from({ length: 8 }, (_, index) => currentYear - index).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))
            )}
          </NativeSelect>
        </Label>
      </div>
      {query.error && (
        <p className="error" role="alert">
          {query.error.message}
        </p>
      )}
      {ready && (
        <>
          <p className="sr-only">
            Use as setas para navegar pelos dias. Enter ou toque abre o resumo; Escape fecha.
          </p>
          <div className="w-full overflow-x-auto py-2">
            <div className="mx-auto w-max min-w-max">
              <div
                className="mb-2 grid gap-x-1 text-xs text-muted-foreground"
                style={{ gridTemplateColumns: `repeat(${weeks},16px)` }}
              >
                {days.map(
                  (row, index) =>
                    row.date.endsWith('-01') && (
                      <span
                        key={row.date}
                        className="whitespace-nowrap"
                        style={{ gridColumn: Math.floor((index + offset) / 7) + 1 }}
                      >
                        {new Date(row.date + 'T12:00:00Z').toLocaleDateString('pt-BR', {
                          month: 'short',
                          timeZone: 'UTC',
                        })}
                      </span>
                    ),
                )}
              </div>
              <div className="grid grid-flow-col auto-cols-[16px] grid-rows-[repeat(7,16px)] gap-1">
                {Array.from({ length: offset }, (_, index) => (
                  <span key={`blank-${index}`} aria-hidden="true" />
                ))}
                {days.map((row, index) => (
                  <Popover
                    key={row.date}
                    open={activeDate === row.date}
                    onOpenChange={(open) => {
                      if (!open)
                        setActiveDate((previous) => (previous === row.date ? null : previous));
                    }}
                  >
                    <PopoverAnchor asChild>
                      <Button
                        type="button"
                        variant="ghost"
                        className={cn(
                          'size-4 min-w-0 rounded-[3px] p-0 hover:brightness-110',
                          levels[levelFor(row.count)],
                        )}
                        data-frequency-date={row.date}
                        tabIndex={firstFocusable === row.date ? 0 : -1}
                        aria-label={`${dayLabel(row.date)}: ${row.count} categorias registradas`}
                        aria-describedby={activeDate === row.date ? tooltipId : undefined}
                        onMouseEnter={() => setActiveDate(row.date)}
                        onMouseLeave={() =>
                          setActiveDate((previous) => (previous === row.date ? null : previous))
                        }
                        onFocus={() => {
                          setFocusedDay(row.date);
                          setActiveDate(row.date);
                        }}
                        onBlur={() =>
                          setActiveDate((previous) => (previous === row.date ? null : previous))
                        }
                        onClick={() => setActiveDate(row.date)}
                        onKeyDown={(event) => moveFocus(event, index)}
                      />
                    </PopoverAnchor>
                    {activeDate === row.date && (
                      <PopoverContent
                        id={tooltipId}
                        role="tooltip"
                        side="top"
                        align="center"
                        collisionPadding={12}
                        className="w-auto max-w-[calc(100vw-24px)] p-3"
                        onOpenAutoFocus={(event) => event.preventDefault()}
                        onCloseAutoFocus={(event) => event.preventDefault()}
                      >
                        <DaySummary row={row} />
                      </PopoverContent>
                    )}
                  </Popover>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>
              Até 4 pontos por dia: sono, alimentação, corrida e força. Cada categoria vale 1 ponto.
            </span>
            <div className="flex items-center gap-1">
              Menos{' '}
              {levels.map((className, index) => (
                <span
                  key={index}
                  className={cn('size-3 rounded-[2px]', className)}
                  aria-hidden="true"
                />
              ))}{' '}
              Mais
            </div>
          </div>
        </>
      )}
    </section>
  );
}
