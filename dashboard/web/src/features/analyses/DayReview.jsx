'use client';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Field } from '@/components/ui/field';
import { Badge } from '@/components/ui/badge';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useId, useRef, useState } from 'react';
import { ErrorNotice, personalApi } from '@/lib/personalApi';

export default function DayReview(props) {
  return <DayReviewForDay key={props.day} {...props} />;
}

function DayReviewForDay({ day, revision, onStateChange }) {
  const fieldPrefix = useId();
  const [draftNotes, setNotes] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const operation = useRef(false),
    previousRevision = useRef(revision),
    queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['day-review', day],
    queryFn: ({ signal }) => personalApi(`day-review/${day}`, undefined, signal),
  });
  const value = query.data,
    loading = query.isPending;
  const notes = draftNotes ?? value?.report?.context?.user_report ?? '';
  useEffect(() => {
    if (previousRevision.current !== revision) {
      previousRevision.current = revision;
      queryClient.invalidateQueries({ queryKey: ['day-review', day] });
    }
  }, [day, revision, queryClient]);
  async function generate() {
    if (operation.current) return;
    operation.current = true;
    const requested = day;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await queryClient.cancelQueries({ queryKey: ['day-review', requested] });
      const result = await personalApi(`day-review/${requested}`, { notes });
      queryClient.setQueryData(['day-review', requested], result);
    } catch (e) {
      setError(e.message);
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(value.report.prompt);
      setMessage('Prompt copiado.');
    } catch {
      setError('Selecione e copie o texto do prompt abaixo.');
    }
  }
  const report = value?.report,
    signal = value?.context?.review_signal;
  const dirty = notes.trim() !== (report?.context?.user_report || '').trim();
  useEffect(() => {
    onStateChange?.({ busy, dirty });
  }, [busy, dirty, onStateChange]);
  return (
    <section className="panel day-review">
      <div className="panel-heading">
        <div>
          <h2>Análise do dia</h2>
          <p>Horário, alimentação, treino e recuperação para decidir os próximos passos.</p>
        </div>
      </div>
      <ErrorNotice error={error || query.error?.message} />
      {signal && (
        <div className="notice">
          <strong>Vale revisar sua energia hoje</strong>
          <p>{signal.message}</p>
          <p className="small muted">
            A diferença para a meta não comprova déficit. A análise considera cobertura, estimativas
            e seu relato.
          </p>
        </div>
      )}
      <Field className="question-label">
        <Label htmlFor={`${fieldPrefix}-day-notes`}>Como foi seu dia? (opcional)</Label>
        <Textarea
          id={`${fieldPrefix}-day-notes`}
          rows="3"
          maxLength="3000"
          disabled={busy}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Ex.: já jantei, estou sem fome e senti pouca energia na corrida. Informe também algo que não registrou."
        />
      </Field>
      <div className="report-actions">
        <Button
          type="button"
          variant="default"
          className="primary"
          disabled={busy || loading || !value?.configured}
          onClick={generate}
        >
          {busy ? 'Analisando seu dia…' : 'Analisar meu dia'}
        </Button>
        {report && (
          <Button type="button" variant="outline" disabled={busy} onClick={copy}>
            Copiar prompt utilizado
          </Button>
        )}
      </div>
      <p className="small muted">
        Ollama local · monta o prompt com os registros e o horário da consulta, explica possíveis
        desequilíbrios e sugere opções. A resposta fica salva; perfil, refeições e metas continuam
        como registrados.
      </p>
      {loading && (
        <p role="status" className="muted">
          Reunindo os registros do dia…
        </p>
      )}
      {busy && (
        <p role="status" className="muted">
          A IA está avaliando alimentação, treino e recuperação…
        </p>
      )}
      {value && !value.configured && (
        <p className="notice">
          Configure o Ollama em Dados e fontes para analisar o dia sem cobrança de API.
        </p>
      )}
      {message && (
        <p role="status" className="small muted">
          {message}
        </p>
      )}
      {report && (
        <article className="assistant-message">
          <div className="assistant-meta">
            <span>Análise de {new Date(report.created_at).toLocaleString('pt-BR')}</span>
            <span>{report.model}</span>
            {value.stale && <Badge variant="outline">Registros alterados</Badge>}
          </div>
          {value.stale && (
            <p className="notice">
              Os dados mudaram após esta resposta. Clique em Analisar meu dia para considerar os
              registros atuais.
            </p>
          )}
          {notes.trim() !== (report.context?.user_report || '') && (
            <p className="small muted">
              O relato acima mudou. Uma nova análise incluirá esse contexto.
            </p>
          )}
          <div className="daily-report">{report.text}</div>
          <details className="method">
            <summary>Ver prompt e dados utilizados</summary>
            <Textarea
              id={`${fieldPrefix}-day-prompt`}
              className="daily-textarea"
              readOnly
              rows="10"
              aria-label="Prompt da análise do dia"
              value={report.prompt}
            />
            <p className="small muted">
              Os valores exatos abaixo são calculados pelo sistema. A IA recebe comparações para
              interpretar o dia.
            </p>
            <Textarea
              id={`${fieldPrefix}-day-audit`}
              className="daily-textarea"
              readOnly
              rows="10"
              aria-label="Registros e cálculos da análise"
              value={JSON.stringify(report.context, null, 2)}
            />
          </details>
          <details className="method">
            <summary>Referências e limites</summary>
            <p>
              A meta e os sinais são estimativas do produto. Estas referências orientam a cautela
              geral, sem validar seu alvo individual.
            </p>
            {(value.references || []).map((item) => (
              <p key={item.url}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>
              </p>
            ))}
          </details>
        </article>
      )}
    </section>
  );
}
