'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import SleepContext from '@/features/sleep/SleepContext';
import { PagedList } from '@/components/shared/ui';
import { Panel, Empty, formatDay } from '@/components/shared/charts';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { personalApi } from '@/lib/personalApi';

const labels = {
  running: 'Corrida',
  strength: 'Força',
  cycling: 'Bike',
  swimming: 'Natação',
  other: 'Outros',
};

export default function DailyAnalysis({ data, onStateChange }) {
  const dates = [
    ...new Set(
      [...(data.activities || []), ...(data.strength || [])].map((row) => row.date).filter(Boolean),
    ),
  ]
    .sort()
    .reverse();
  const [day, setDay] = useState(dates[0] || data.as_of);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''),
    [manual, setManual] = useState(''),
    [manualFingerprint, setManualFingerprint] = useState(null),
    [copied, setCopied] = useState(false);
  const operation = useRef(false),
    queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['daily-analysis', day],
    queryFn: ({ signal }) => personalApi(`daily-analysis/${day}`, undefined, signal),
    enabled: Boolean(day),
  });
  const result = query.data,
    loading = query.isPending || query.isFetching;
  const notice = error || query.error?.message || '';
  useEffect(() => {
    onStateChange?.({ busy, dirty: Boolean(manual.trim()) });
  }, [busy, manual, onStateChange]);
  function resetDraft() {
    setError('');
    setCopied(false);
    setManual('');
    setManualFingerprint(null);
  }
  async function load() {
    resetDraft();
    await query.refetch();
  }

  async function generate(imported = false) {
    if (operation.current || !result) return;
    operation.current = true;
    setBusy(true);
    setError('');
    const requestedDay = day;
    try {
      const report = await personalApi(`daily-analysis/${requestedDay}`, {
        fingerprint: imported ? manualFingerprint || result.fingerprint : result.fingerprint,
        ...(imported ? { text: manual } : {}),
      });
      queryClient.setQueryData(['daily-analysis', requestedDay], (previous) => ({
        ...(previous || result),
        report,
        stale: false,
      }));
      setManual('');
      setManualFingerprint(null);
    } catch (error) {
      if (error.status === 409) await query.refetch();
      setError(error.message);
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(result.prompt);
      setManualFingerprint(result.fingerprint);
      setCopied(true);
    } catch {
      setError(
        'Não foi possível copiar automaticamente. Selecione o texto do prompt abaixo e copie.',
      );
    }
  }
  function discardAllowed() {
    return !manual.trim() || window.confirm('Descartar a resposta ainda não salva?');
  }

  return (
    <div className="space-y-5">
      <Panel
        title="Análise diária por IA"
        sub="Corrida, força e outras atividades em uma análise conjunta, com contexto da carga recente."
      >
        <div className="flex flex-wrap items-end gap-4">
          <label className="space-y-2 text-sm">
            Dia do treino
            <Input
              type="date"
              value={day}
              disabled={busy}
              onChange={(event) => {
                if (discardAllowed()) {
                  resetDraft();
                  setDay(event.target.value);
                }
              }}
            />
          </label>
          <Button
            variant="outline"
            disabled={busy || loading || !day}
            onClick={() => {
              if (discardAllowed()) load();
            }}
          >
            Consultar novamente
          </Button>
        </div>
        {notice && (
          <p className="error" role="alert">
            {notice}
          </p>
        )}
        {loading && (
          <p className="text-sm text-muted-foreground" role="status">
            Reunindo os treinos…
          </p>
        )}
        {result && (
          <>
            <p className="text-sm">
              <strong>{result.context.session_count} sessões</strong> ·{' '}
              {result.context.activities
                .map((activity) => labels[activity.kind] || activity.type || 'Outros')
                .concat(result.context.strength.map(() => 'Força'))
                .join(' · ') || 'Sem treinos registrados'}
            </p>
            <PagedList
              items={[
                ...result.context.activities.map((activity) => ({
                  ...activity,
                  sessionKind: 'activity',
                })),
                ...result.context.strength.map((strength) => ({
                  ...strength,
                  sessionKind: 'strength',
                })),
              ]}
              resetKey={day}
              label="treinos do dia"
            >
              {(rows) => (
                <div className="grid gap-3 sm:grid-cols-2">
                  {rows.map((session, index) => (
                    <div
                      className="rounded-lg border bg-muted/30 p-4 text-sm"
                      key={session.id || index}
                    >
                      <strong>
                        {session.title || session.name || labels[session.kind] || 'Atividade'}
                      </strong>
                      {session.sessionKind === 'strength' ? (
                        <p className="mt-2 text-muted-foreground">
                          {session.working_sets ?? 'Sem dado de'} séries de trabalho ·{' '}
                          {session.volume_kg ?? 'Sem dado de'} kg de volume
                        </p>
                      ) : (
                        <p className="mt-2 text-muted-foreground">
                          {session.elapsed_time || 'Duração indisponível'}
                          {session.distance_km != null ? ` · ${session.distance_km} km` : ''}
                          {session.avg_hr != null ? ` · FC média ${session.avg_hr} bpm` : ''}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </PagedList>
            {!result.context.session_count && (
              <Empty>
                Não há registros nessa data. Escolha outro dia ou atualize seus treinos.
              </Empty>
            )}
            <SleepContext sleep={result.context.sleep} />
            <p className="text-xs leading-relaxed text-muted-foreground">
              A análise usa o provedor de IA configurado em Dados e fontes. O período termina no dia
              selecionado; referências anteriores de sono aparecem com suas datas.
            </p>
            {!result.configured && (
              <div className="notice">
                Geração automática ainda não configurada. Você já pode copiar o prompt, pedir a
                análise no ChatGPT ou em outra IA e importar a resposta abaixo.
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={busy || loading || !result.configured || !result.context.session_count}
                onClick={() => generate()}
              >
                {busy ? 'Salvando análise…' : 'Gerar análise com IA'}
              </Button>
              <Button
                variant="outline"
                disabled={busy || loading || !result.context.session_count}
                onClick={copy}
              >
                {copied ? 'Prompt copiado' : 'Copiar prompt'}
              </Button>
            </div>
            <details className="method">
              <summary>Ver prompt e dados enviados</summary>
              <Textarea aria-label="Prompt da análise" readOnly value={result.prompt} rows={14} />
            </details>
            <details className="method">
              <summary>Importar resposta de uma IA</summary>
              <p className="text-xs text-muted-foreground">
                Cole a resposta produzida com o prompt desta data. Ela ficará identificada como
                resposta importada.
              </p>
              <Textarea
                aria-label="Resposta da IA"
                rows={10}
                value={manual}
                disabled={busy}
                onChange={(event) => {
                  if (!manual.trim()) setManualFingerprint(result.fingerprint);
                  setManual(event.target.value);
                }}
                placeholder="Cole o relatório aqui…"
              />
              <Button
                variant="outline"
                disabled={
                  busy ||
                  loading ||
                  manual.trim().length < 20 ||
                  manual.length > 30000 ||
                  !result.context.session_count
                }
                onClick={() => generate(true)}
              >
                Salvar e exibir relatório
              </Button>
            </details>
          </>
        )}
      </Panel>
      {result?.report && (
        <Panel
          title={`Relatório do dia · ${formatDay(day)}`}
          sub={`${result.report.model} · ${new Date(result.report.generated_at).toLocaleString('pt-BR')}`}
        >
          {result.stale && (
            <div className="notice">
              Os dados mudaram desde esta análise. Gere um novo relatório ou importe uma nova
              resposta com o prompt atualizado.
            </div>
          )}
          <article className="whitespace-pre-wrap text-sm leading-relaxed">
            {result.report.text}
          </article>
          <p className="text-xs text-muted-foreground">
            Interpretação por IA: efeitos prováveis, não ganhos medidos nem avaliação médica.
          </p>
        </Panel>
      )}
    </div>
  );
}
