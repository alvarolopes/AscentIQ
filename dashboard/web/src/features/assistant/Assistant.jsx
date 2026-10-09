'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { NativeSelect } from '@/components/ui/native-select';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  array,
  dayLabel,
  ErrorNotice,
  PageHeading,
  personalApi,
  StatusNotice,
  today,
} from '@/lib/personalApi';
import { PagedList } from '@/components/shared/ui';
import { newId } from '@/lib/ids';

export default function Assistant({ compact = false, day: initialDay = '' }) {
  const questionId = useId();
  const [day, setDay] = useState(initialDay || ''),
    [period, setPeriod] = useState('day'),
    [days, setDays] = useState(14);
  const [start, setStart] = useState(initialDay || ''),
    [end, setEnd] = useState(initialDay || ''),
    [includeMedical, setIncludeMedical] = useState(false);
  const [question, setQuestion] = useState(''),
    [manual, setManual] = useState(''),
    [manualFingerprint, setManualFingerprint] = useState(null);
  const [context, setContext] = useState(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  const [conversationLoading, setConversationLoading] = useState(true);
  const [error, setError] = useState(''),
    [conflict, setConflict] = useState(''),
    [message, setMessage] = useState(''),
    [conversation, setConversation] = useState('');
  const [records, setRecords] = useState([]),
    [pagination, setPagination] = useState({ page: 1, page_size: 10, pages: 1, total: 0 });
  const [past, setPast] = useState([]),
    [pastPagination, setPastPagination] = useState({ page: 1, page_size: 10, pages: 1, total: 0 });
  const [showPast, setShowPast] = useState(false),
    [refresh, setRefresh] = useState(0);
  const sequence = useRef(0),
    historySequence = useRef(0),
    pastSequence = useRef(0),
    references = useRef([]),
    sending = useRef(false);
  useEffect(() => {
    const selected = initialDay || today();
    setDay(selected);
    setStart((value) => value || selected);
    setEnd((value) => value || selected);
  }, [initialDay]);
  useEffect(() => {
    setConversation((value) => value || newId());
  }, []);
  const scope = useCallback(
    () => ({
      day,
      period,
      days,
      include_medical: includeMedical,
      ...(period === 'custom' ? { start, end } : {}),
    }),
    [day, period, days, includeMedical, start, end],
  );
  const fetchContext = useCallback(
    (signal) => personalApi('assistant/context?' + new URLSearchParams(scope()), undefined, signal),
    [scope],
  );

  useEffect(() => {
    // A scope change clears the previous conflict; its automatic refresh does not.
    setConflict('');
  }, [fetchContext]);

  useEffect(() => {
    if (!day) return;
    const version = ++sequence.current;
    const request = new AbortController();
    setLoading(true);
    setContext(null);
    setError('');
    fetchContext(request.signal)
      .then((value) => {
        if (!request.signal.aborted && version === sequence.current) setContext(value);
      })
      .catch((e) => {
        if (!request.signal.aborted && version === sequence.current) setError(e.message);
      })
      .finally(() => {
        if (!request.signal.aborted && version === sequence.current) setLoading(false);
      });
    return () => {
      request.abort();
    };
  }, [day, fetchContext, refresh]);

  const loadConversation = useCallback(
    async (page = 1, pageSize = 10, signal) => {
      if (!conversation) return;
      const version = ++historySequence.current;
      const response = await personalApi(
        'assistant/history?' +
          new URLSearchParams({ conversation_id: conversation, page, page_size: pageSize }),
        undefined,
        signal,
      );
      if (signal?.aborted || version !== historySequence.current) return;
      const rows = array(response.history);
      setRecords(rows);
      setPagination(response.pagination);
      if (response.pagination.page === 1)
        references.current = rows
          .slice(0, 3)
          .reverse()
          .map((row) => row.id);
    },
    [conversation],
  );
  useEffect(() => {
    if (!conversation) return;
    let active = true;
    const request = new AbortController();
    references.current = [];
    setRecords([]);
    setConversationLoading(true);
    loadConversation(1, 10, request.signal)
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setConversationLoading(false);
      });
    return () => {
      active = false;
      request.abort();
    };
  }, [conversation, loadConversation]);

  async function loadPast(page = 1, pageSize = 10) {
    const version = ++pastSequence.current;
    try {
      const response = await personalApi(`assistant/history?page=${page}&page_size=${pageSize}`);
      if (version !== pastSequence.current) return;
      setPast(array(response.history));
      setPastPagination(response.pagination);
    } catch (e) {
      if (version === pastSequence.current) setError(e.message);
    }
  }
  async function send(imported = false) {
    if (sending.current || !conversation || !day) return;
    sending.current = true;
    setBusy(true);
    setError('');
    setConflict('');
    setMessage('');
    const text = question.trim();
    const requestScope = scope(),
      requestConversation = conversation,
      contextVersion = sequence.current;
    try {
      // Imported answers retain the fingerprint of the context actually reviewed.
      const fresh = await personalApi('assistant/context?' + new URLSearchParams(requestScope));
      if (contextVersion === sequence.current) setContext(fresh);
      const previous = await personalApi(
        'assistant/history?' +
          new URLSearchParams({ conversation_id: requestConversation, page: 1, page_size: 10 }),
      );
      references.current = array(previous.history)
        .slice(0, 3)
        .reverse()
        .map((row) => row.id);
      const fingerprint = imported ? manualFingerprint || context?.fingerprint : fresh.fingerprint;
      const value = await personalApi('assistant', {
        ...requestScope,
        question: text,
        conversation_id: requestConversation,
        message_ids: references.current,
        fingerprint,
        ...(imported ? { manual_response: manual.trim() } : {}),
      });
      references.current = [...references.current, value.id].slice(-3);
      setQuestion('');
      setManual('');
      setManualFingerprint(null);
      setMessage(
        value.withheld_medical_turns
          ? 'Respostas anteriores com dados médicos não foram reenviadas sem a autorização atual.'
          : value.cached
            ? 'Resposta recuperada para esta conversa.'
            : 'Resposta salva. Seu plano e seus registros permanecem sob seu controle.',
      );
      await loadConversation(1, pagination.page_size);
      if (showPast) await loadPast(1, pastPagination.page_size);
    } catch (e) {
      if (e.status === 409) {
        setConflict(
          e.message + ' Sua pergunta foi mantida. Revise o contexto atualizado e tente novamente.',
        );
        setRefresh((v) => v + 1);
      } else setError(e.message);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  const prompt = (question ? 'PERGUNTA: ' + question + '\n\n' : '') + (context?.prompt || '');
  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt);
      setManualFingerprint(context.fingerprint);
      setMessage('Pergunta e contexto copiados.');
    } catch {
      setError('Selecione o texto do contexto e copie manualmente.');
    }
  }
  function beginConversation() {
    references.current = [];
    setConversationLoading(true);
    setConversation(newId());
    setMessage('Nova conversa iniciada. Seu rascunho foi mantido.');
  }
  const chosen = context?.context?.period;
  const selected = context?.context?.selection;
  const turn = (row) => (
    <article className="assistant-message" key={row.id}>
      <div className="assistant-meta">
        <span>{dayLabel(row.date || row.created_at)}</span>
        <span>{row.source === 'imported' ? 'Resposta importada' : row.model}</span>
      </div>
      <h3>{row.question}</h3>
      <div className="daily-report">{row.text || 'Resposta indisponível.'}</div>
    </article>
  );
  return (
    <div className={'assistant-content' + (compact ? ' compact' : '')}>
      {!compact && (
        <PageHeading kicker="ASSISTENTE" title="Converse com seu contexto.">
          Consulte seus registros e continue a conversa sem alterar automaticamente seu plano.
        </PageHeading>
      )}
      <ErrorNotice error={error} />
      <ErrorNotice error={conflict} />
      <StatusNotice message={message} />
      <div className="filters assistant-scope">
        <Label className="items-stretch">
          Contexto
          <NativeSelect
            className="w-full min-w-0"
            value={period}
            disabled={busy}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="day">Dia</option>
            <option value="month">Mês</option>
            <option value="goals">Objetivos</option>
            <option value="days">Últimos dias</option>
            <option value="custom">Período definido</option>
          </NativeSelect>
        </Label>
        {period === 'custom' ? (
          <>
            <Label className="items-stretch">
              De
              <Input
                type="date"
                value={start}
                disabled={busy}
                onChange={(e) => setStart(e.target.value)}
              />
            </Label>
            <Label className="items-stretch">
              Até
              <Input
                type="date"
                value={end}
                disabled={busy}
                onChange={(e) => setEnd(e.target.value)}
              />
            </Label>
          </>
        ) : (
          <Label className="items-stretch">
            {period === 'month' ? 'Mês de referência' : 'Data'}
            <Input
              type="date"
              value={day}
              disabled={busy}
              onChange={(e) => setDay(e.target.value)}
            />
          </Label>
        )}
        {period === 'days' && (
          <Label className="items-stretch">
            Período
            <NativeSelect
              className="w-full min-w-0"
              value={days}
              disabled={busy}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value="7">7 dias</option>
              <option value="14">14 dias</option>
              <option value="30">30 dias</option>
            </NativeSelect>
          </Label>
        )}
      </div>
      {loading ? (
        <p className="small muted" role="status">
          Reunindo os registros…
        </p>
      ) : (
        chosen && (
          <p className="small muted">
            {dayLabel(chosen.from)} a {dayLabel(chosen.to)} · Os dados são atualizados antes de cada
            pergunta.
          </p>
        )
      )}
      <div className="question-label">
        <Label htmlFor={questionId}>Sua pergunta</Label>
        <Textarea
          id={questionId}
          rows={compact ? 3 : 4}
          maxLength="5000"
          value={question}
          disabled={busy}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ex.: como minha alimentação deste mês se relaciona com meu objetivo?"
        />
      </div>
      <div className="report-actions">
        <Button
          variant="default"
          className="primary"
          disabled={
            busy ||
            loading ||
            conversationLoading ||
            !context ||
            question.trim().length < 3 ||
            context.configured === false
          }
          onClick={() => send()}
        >
          {busy
            ? 'Preparando resposta…'
            : conversationLoading
              ? 'Reunindo a conversa…'
              : 'Perguntar à IA'}
        </Button>
        <Button variant="outline" disabled={busy} onClick={beginConversation}>
          Nova conversa
        </Button>
      </div>
      {context?.configured === false && (
        <p className="notice">
          Configure a IA em Dados e fontes ou copie o contexto e importe uma resposta.
        </p>
      )}
      <details className="method">
        <summary>Contexto e opções</summary>
        <p className="small muted">
          Seu perfil, objetivos, plano, alimentação, treinos, carga, sono e check-ins entram quando
          disponíveis. A conversa considera trechos de até três respostas recentes. Força inclui
          nomes dos exercícios e totais, sem todas as séries. Dados médicos e documentos só entram
          com a autorização abaixo.
        </p>
        <Label htmlFor="assistant-medical-consent" className="checkbox-label">
          <Checkbox
            id="assistant-medical-consent"
            disabled={busy}
            checked={includeMedical}
            onCheckedChange={(checked) => setIncludeMedical(checked === true)}
          />
          Incluir referências médicas e documentos registrados
        </Label>
        {selected && (
          <p className="small muted">
            Resumos cobrem todo o período. Detalhes selecionados: {selected.meal_details_included}/
            {selected.meal_detail_count} refeições, {selected.activities_included}/
            {selected.activity_count} atividades, {selected.strength_included}/
            {selected.strength_count} sessões de força, {selected.goals_included}/
            {selected.goal_count} objetivos e {selected.plans_included}/{selected.plan_count}{' '}
            planos.{' '}
            {selected.primary_goal_always_included && 'O objetivo principal foi preservado. '}
            {!selected.all_daily_totals_included &&
              'As séries diárias foram resumidas para caber no modelo; os totais do período foram preservados. '}
            Para um detalhe antigo, selecione sua data.
          </p>
        )}
        {selected?.body_details_included === false && (
          <p className="small muted">
            As medidas corporais foram reduzidas às referências principais com suas datas.
          </p>
        )}
        {selected?.plan_rationale_included === false && (
          <p className="small muted">
            As metas numéricas do plano estão incluídas. A justificativa extensa está disponível em
            Objetivos; selecione um período menor para incluí-la no contexto.
          </p>
        )}
        <div className="report-actions">
          <Button
            variant="outline"
            disabled={busy || loading}
            onClick={() => setRefresh((v) => v + 1)}
          >
            Atualizar contexto
          </Button>
          <Button variant="outline" disabled={!context || busy} onClick={copy}>
            Copiar contexto
          </Button>
        </div>
        <details className="method">
          <summary>Ver dados enviados</summary>
          <Textarea
            className="daily-textarea"
            readOnly
            aria-label="Contexto do assistente"
            rows="8"
            value={prompt}
          />
        </details>
        <details className="method">
          <summary>Importar resposta de outra IA</summary>
          <p className="small muted">
            Use a pergunta e o contexto copiados. Se os dados mudarem, uma nova revisão será
            necessária.
          </p>
          <Textarea
            aria-label="Resposta de outra IA"
            rows="4"
            maxLength="30000"
            value={manual}
            disabled={busy}
            onChange={(e) => {
              setManual(e.target.value);
              if (!manualFingerprint) setManualFingerprint(context?.fingerprint);
            }}
          />
          <Button
            variant="outline"
            disabled={
              busy ||
              loading ||
              conversationLoading ||
              !context ||
              question.trim().length < 3 ||
              manual.trim().length < 20
            }
            onClick={() => send(true)}
          >
            Salvar resposta importada
          </Button>
        </details>
      </details>
      <section className="assistant-conversation" aria-label="Conversa atual" aria-live="polite">
        <h2>Conversa atual</h2>
        <PagedList
          items={records}
          pagination={pagination}
          onPageChange={(page) =>
            loadConversation(page, pagination.page_size).catch((e) => setError(e.message))
          }
          onPageSizeChange={(size) => loadConversation(1, size).catch((e) => setError(e.message))}
          label="respostas"
          empty="Sua primeira pergunta inicia a conversa."
        >
          {(rows) => rows.map(turn)}
        </PagedList>
      </section>
      <details
        className="method"
        onToggle={(e) => {
          setShowPast(e.currentTarget.open);
          if (e.currentTarget.open) loadPast();
        }}
      >
        <summary>Conversas anteriores</summary>
        <PagedList
          items={past}
          pagination={pastPagination}
          onPageChange={(page) => loadPast(page, pastPagination.page_size)}
          onPageSizeChange={(size) => loadPast(1, size)}
          label="respostas anteriores"
          empty="Nenhuma conversa anterior."
        >
          {(rows) =>
            rows.map((row) => (
              <div key={row.id}>
                {turn(row)}
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setQuestion((existing) => existing || row.question || '');
                    if (row.conversation_id && row.conversation_id !== conversation) {
                      setConversationLoading(true);
                      setConversation(row.conversation_id);
                    }
                    setMessage(
                      'Conversa selecionada. Seu rascunho foi mantido; o contexto será atualizado antes da próxima pergunta.',
                    );
                  }}
                >
                  Continuar esta conversa
                </Button>
              </div>
            ))
          }
        </PagedList>
      </details>
    </div>
  );
}
