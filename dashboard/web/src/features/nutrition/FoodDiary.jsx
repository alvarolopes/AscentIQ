'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Field } from '@/components/ui/field';
import { NativeSelect } from '@/components/ui/native-select';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Image from 'next/image';
import { newId } from '@/lib/ids';
import React, { useEffect, useId, useRef, useState } from 'react';
import DayReview from '@/features/analyses/DayReview';
import { Modal, PagedList } from '@/components/shared/ui';
import {
  array,
  dayLabel,
  ErrorNotice,
  format,
  personalApi,
  StatusNotice,
  today,
} from '@/lib/personalApi';

const nutrients = {
  kcal: 'Calorias (kcal)',
  protein_g: 'Proteína (g)',
  carbs_g: 'Carboidratos (g)',
  fat_g: 'Gorduras (g)',
};
const meals = ['Café da manhã', 'Almoço', 'Lanche', 'Jantar', 'Ceia', 'Outro'];
const emptyEntry = () => ({
  id: '',
  meal: 'Lanche',
  text: '',
  analysis: null,
  image: null,
  save_token: '',
});
const blank = () => ({ ...emptyEntry(), id: newId(), save_token: newId() });
const clone = (value) => JSON.parse(JSON.stringify(value));
const draftSignature = (entry, title = '', servings = 1) =>
  JSON.stringify({ meal: entry.meal, text: entry.text, image: entry.image, title, servings });
const excerpt = (value, length = 240) =>
  value.length > length ? value.slice(0, length).trimEnd() + '…' : value;
function sum(items, key) {
  const known = array(items).filter((item) => item[key] != null);
  return known.length ? known.reduce((value, item) => value + Number(item[key]), 0) : null;
}
function totalLabel(diary, key) {
  if (!diary.entries.length) return diary.fasting_declared ? '0' : 'Sem dado';
  const known = diary.entries.some((entry) =>
    array(entry.analysis?.items).some((item) => item[key] != null),
  );
  return known ? format(diary.totals[key], 0) : 'Pendente';
}
function isPending(row) {
  return (
    !row.analysis ||
    !array(row.analysis.items).length ||
    row.analysis.items.some((item) => item.kcal == null)
  );
}
function FoodEstimate({ analysis, resetKey }) {
  return (
    <>
      <PagedList items={array(analysis.items)} resetKey={resetKey} label="Alimentos estimados">
        {(items) =>
          items.map((item, index) => (
            <p key={index}>
              {item.name}: {format(item.kcal)} kcal · P {format(item.protein_g)} g · C{' '}
              {format(item.carbs_g)} g · G {format(item.fat_g)} g
            </p>
          ))
        }
      </PagedList>
      {analysis.notes && <p>{analysis.notes}</p>}
    </>
  );
}

export default function FoodDiary({ initialDay }) {
  const fieldPrefix = useId();
  const [day, setDay] = useState(initialDay || today()),
    [entry, setEntry] = useState(emptyEntry),
    [editing, setEditing] = useState(false),
    [editorOpen, setEditorOpen] = useState(false);
  const [recipeTitle, setRecipeTitle] = useState(''),
    [servings, setServings] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [fastingDraft, setFasting] = useState(null);
  const [portions, setPortions] = useState({}),
    [reviewOpen, setReviewOpen] = useState(false),
    [reviewState, setReviewState] = useState({ busy: false, dirty: false }),
    [readingImage, setReadingImage] = useState(false);
  const [initialDraft, setInitialDraft] = useState('');
  const operation = useRef(false),
    editorFocusRef = useRef(null),
    queryClient = useQueryClient();
  const diaryQuery = useQuery({
    queryKey: ['food', day],
    queryFn: ({ signal }) => personalApi('food/' + day, undefined, signal),
  });
  const libraryQuery = useQuery({
    queryKey: ['food-library'],
    queryFn: ({ signal }) => personalApi('food-library', undefined, signal),
  });
  const targetsQuery = useQuery({
    queryKey: ['nutrition-targets', day],
    queryFn: ({ signal }) => personalApi(`nutrition-targets/${day}`, undefined, signal),
    refetchInterval: 15000,
  });
  const configQuery = useQuery({
    queryKey: ['ai-configuration'],
    queryFn: ({ signal }) => personalApi('ai/configuration', undefined, signal),
  });
  const diary = diaryQuery.data
    ? {
        ...diaryQuery.data,
        targets: targetsQuery.data ?? diaryQuery.data.targets,
        ...configQuery.data,
      }
    : null;
  const recipes = array(libraryQuery.data?.recipes),
    loading = diaryQuery.isPending;
  const fasting = fastingDraft ?? Boolean(diaryQuery.data?.fasting_declared);
  function setDiary(update) {
    queryClient.setQueryData(['food', day], update);
  }
  async function load(selectedDay = day) {
    return queryClient.fetchQuery({
      queryKey: ['food', selectedDay],
      queryFn: ({ signal }) => personalApi('food/' + selectedDay, undefined, signal),
      staleTime: 0,
    });
  }
  async function loadLibrary() {
    await queryClient.invalidateQueries({ queryKey: ['food-library'] });
  }
  function changeDay(nextDay) {
    setDay(nextDay);
    setEntry(emptyEntry());
    setEditing(false);
    setEditorOpen(false);
    setReviewOpen(false);
    setError('');
    setMessage('');
    setFasting(null);
  }
  useEffect(() => {
    const refresh = () => queryClient.invalidateQueries({ queryKey: ['ai-configuration'] });
    const storage = (event) => {
      if (event.key === 'ascentiq-integrations-updated') refresh();
    };
    window.addEventListener('storage', storage);
    window.addEventListener('ascentiq-integrations-changed', refresh);
    return () => {
      window.removeEventListener('storage', storage);
      window.removeEventListener('ascentiq-integrations-changed', refresh);
    };
  }, [queryClient]);
  async function run(action) {
    if (operation.current) return null;
    operation.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      return await action();
    } catch (e) {
      setError(e.message);
      if (e.status === 409 || /diário mudou/i.test(e.message)) await load().catch(() => {});
      return null;
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  function reset() {
    setEntry(blank());
    setEditing(false);
    setRecipeTitle('');
    setServings(1);
  }
  function openEditor(value = blank(), isEditing = false, isUnsaved = false) {
    editorFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEntry(value);
    setEditing(isEditing);
    setRecipeTitle('');
    setServings(1);
    setInitialDraft(draftSignature(isUnsaved ? emptyEntry() : value));
    setError('');
    setMessage('');
    setEditorOpen(true);
  }
  function closeEditor() {
    setEditorOpen(false);
    reset();
  }
  function input(key, value) {
    setEntry((previous) => ({
      ...previous,
      [key]: value,
      save_token: newId(),
      ...(key === 'text' ? { analysis: null } : {}),
    }));
  }
  async function save() {
    if (readingImage) return;
    await run(async () => {
      await queryClient.cancelQueries({ queryKey: ['food', day] });
      const result = await personalApi(`food/${day}/save`, {
        id: entry.id,
        meal: entry.meal,
        text:
          entry.text.trim().length >= 3
            ? entry.text.trim()
            : 'Refeição registrada por foto. ' + entry.text.trim(),
        image: entry.image,
        estimate_on_save: true,
        save_token: entry.save_token,
        revision: diary.revision,
      });
      setDiary((value) => ({ ...value, ...result }));
      queryClient.invalidateQueries({ queryKey: ['day-review', day] });
      queryClient.invalidateQueries({ queryKey: ['nutrition-targets', day] });
      setFasting(null);
      if (result.analysis_status === 'estimated') {
        closeEditor();
        setMessage('Refeição salva com estimativa da IA. O total do dia foi atualizado.');
      } else {
        const stored = array(result.entries).find((row) => row.id === entry.id);
        const saved = { ...entry, ...stored, image: entry.image, save_token: newId() };
        setEntry(saved);
        setEditing(true);
        setInitialDraft(draftSignature(saved));
        setMessage('Refeição salva. A estimativa ficou pendente.');
        setError(
          'A IA não concluiu a estimativa. ' +
            (result.analysis_error || 'Salve novamente para tentar.'),
        );
      }
    });
  }
  async function imageSelected(file) {
    setError('');
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Escolha uma foto JPEG, PNG ou WebP.');
      return;
    }
    if (file.size > 6 * 1024 * 1024) {
      setError('A foto deve ter até 6 MB.');
      return;
    }
    setReadingImage(true);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 16384)
        binary += String.fromCharCode(...bytes.subarray(i, i + 16384));
      setEntry((value) => ({
        ...value,
        image: `data:${file.type};base64,${btoa(binary)}`,
        analysis: null,
        save_token: newId(),
      }));
    } catch {
      setError('Não foi possível ler a foto.');
    } finally {
      setReadingImage(false);
    }
  }
  function edit(row, copy = false) {
    openEditor(
      {
        ...clone(row),
        analysis: row.analysis || row.analysis_proposal,
        id: copy ? newId() : row.id,
        image: null,
        image_id: copy ? null : row.image_id,
        save_token: newId(),
      },
      !copy,
      copy,
    );
    setMessage(
      copy
        ? 'Cópia da descrição preparada. Revise, adicione uma foto se desejar e salve como uma nova refeição.'
        : 'Edite a descrição e salve. A IA recalcula a estimativa automaticamente.',
    );
  }
  function prepareRecipe(recipe) {
    const selected = Number(portions[recipe.id] || 1),
      yielded = Number(recipe.servings || 1);
    if (!Number.isFinite(selected) || selected <= 0 || selected > 1000) {
      setError('Informe de 0,1 a 1.000 porções para usar a receita.');
      return;
    }
    const factor = selected / yielded,
      analysis = recipe.analysis ? clone(recipe.analysis) : null;
    if (analysis) {
      analysis.items = analysis.items.map((item) => ({
        ...item,
        name: `${item.name} · ${selected} de ${yielded} porções`,
        ...Object.fromEntries(
          Object.keys(nutrients).map((key) => [
            key,
            item[key] == null ? null : Math.round(Number(item[key]) * factor * 10) / 10,
          ]),
        ),
      }));
      analysis.notes = `${analysis.notes || ''}\nReceita escalada para ${selected} de ${yielded} porções. Revise as quantidades.`;
    }
    openEditor(
      {
        ...blank(),
        text: `${recipe.text}\nConsumi ${selected} de ${yielded} porções da receita.`,
        analysis,
      },
      false,
      true,
    );
    setMessage('Porção da receita preparada. Confira e salve a refeição.');
  }
  async function saveRecipe() {
    await run(async () => {
      await personalApi('food-library', {
        title: recipeTitle.trim(),
        text: entry.text,
        servings,
        analysis: entry.analysis,
      });
      await loadLibrary();
      setRecipeTitle('');
      setServings(1);
      setMessage('Refeição salva na biblioteca.');
    });
  }
  const pending = diary?.pending_count || 0,
    analysis = entry.analysis,
    canSave = entry.text.trim().length >= 3 || Boolean(entry.image);
  const dirty = draftSignature(entry, recipeTitle, servings) !== initialDraft;
  return (
    <>
      <ErrorNotice
        error={editorOpen ? '' : error || diaryQuery.error?.message || libraryQuery.error?.message}
      />
      <StatusNotice message={editorOpen ? '' : message} />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Nutrition</h2>
            <p>consumo e metas</p>
          </div>
        </div>
        <div className="filters">
          <Label>
            Dia
            <Input
              type="date"
              value={day}
              disabled={busy || editorOpen || reviewOpen}
              onChange={(e) => changeDay(e.target.value)}
            />
          </Label>
          <Button
            type="button"
            variant="outline"
            disabled={busy || loading}
            onClick={() => run(load)}
          >
            Atualizar o diário
          </Button>
          <Badge variant={diary?.completeness === 'complete' ? 'default' : 'secondary'}>
            {{
              empty: 'Sem registros',
              partial: 'Diário parcial',
              complete: 'Dia declarado completo',
            }[diary?.completeness] || 'Consultando'}
          </Badge>
        </div>
      </section>
      {loading && (
        <p className="muted" role="status">
          Reunindo seu diário…
        </p>
      )}
      {diary && (
        <>
          <div className="metrics four daily-nutrition-progress">
            {Object.entries(nutrients).map(([key, label]) => {
              const target = diary.targets?.[key],
                known =
                  Boolean(diary.fasting_declared) ||
                  diary.entries.some((row) =>
                    array(row.analysis?.items).some((item) => item[key] != null),
                  ),
                consumed = known ? Number(diary.totals[key] || 0) : null,
                remaining = target != null && known ? target - consumed : null;
              return (
                <div className="metric" key={key}>
                  <div className="eyebrow">{label}</div>
                  <div className="metric-value">
                    {diary.entries.length
                      ? totalLabel(diary, key)
                      : diary.fasting_declared
                        ? '0'
                        : 'Sem dado'}
                    {target != null && <span className="target-total"> / {format(target, 0)}</span>}
                  </div>
                  {target != null && known && (
                    <Progress
                      aria-label={`Progresso de ${label}`}
                      aria-valuetext={`${format(consumed, 0)} de ${format(target, 0)}`}
                      value={
                        target > 0
                          ? Math.min(100, (consumed / target) * 100)
                          : consumed > 0
                            ? 100
                            : 0
                      }
                    />
                  )}
                  <p className="small muted">
                    {remaining != null
                      ? remaining >= 0
                        ? `Faltam ${format(remaining, 0)} ${key === 'kcal' ? 'kcal' : 'g'}`
                        : `${format(-remaining, 0)} ${key === 'kcal' ? 'kcal' : 'g'} acima da meta`
                      : !known
                        ? diary.entries.length
                          ? 'Estimativa pendente · saldo ainda indisponível'
                          : 'Registre o consumo para calcular o saldo'
                        : 'Total registrado · meta ainda não disponível'}
                    {known && diary.unknown_nutrients?.[key]
                      ? ` · saldo provisório, ${diary.unknown_nutrients[key]} estimativa(s) pendente(s)`
                      : ''}
                  </p>
                </div>
              );
            })}
          </div>
          <div className="nutrition-target-notice">
            <p className="small muted">
              Registrado / meta do dia ·{' '}
              {diary.targets?.automatic
                ? 'meta atualizada diariamente conforme peso, objetivo e treinos'
                : 'meta automática pausada'}
              .
              {diary.targets?.updated_at
                ? ` Última atualização: ${new Date(diary.targets.updated_at).toLocaleString('pt-BR')}.`
                : ''}
            </p>
            {diary.targets?.message && <p role="status">{diary.targets.message}</p>}
            {diary.targets?.reason && (
              <details className="method">
                <summary>Como sua meta foi definida</summary>
                <p>{diary.targets.reason}</p>
                {array(diary.targets.limitations).map((text, index) => (
                  <p className="small muted" key={index}>
                    {text}
                  </p>
                ))}
              </details>
            )}
          </div>
          {(!diary.complete_nutrition || pending > 0) && (
            <p className="small muted" role="status">
              {pending
                ? `${pending} refeição(ões) com estimativa pendente. `
                : 'Diário em andamento. '}
              O subtotal conhecido ainda pode ser parcial.
            </p>
          )}
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Refeições de {dayLabel(day)}</h2>
                <p>Salve a descrição ou a foto para estimar automaticamente.</p>
              </div>
              <div className="report-actions">
                <Button
                  type="button"
                  variant="default"
                  className="primary"
                  disabled={busy}
                  onClick={() => openEditor()}
                >
                  Adicionar refeição
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setReviewState({ busy: false, dirty: false });
                    setReviewOpen(true);
                  }}
                >
                  Analisar meu dia
                </Button>
              </div>
            </div>
            {diary.entries.length ? (
              <PagedList items={diary.entries} resetKey={day} label="Refeições">
                {(items) => (
                  <div className="meal-grid">
                    {items.map((row) => (
                      <article className="food-entry meal-card" key={row.id}>
                        <div className="proposal-heading">
                          <h3>{row.meal}</h3>
                          <Badge variant={isPending(row) ? 'secondary' : 'outline'}>
                            {isPending(row)
                              ? row.analysis_proposal
                                ? 'Estimativa para revisão'
                                : 'Estimativa pendente'
                              : row.source === 'ai_estimated'
                                ? 'Estimativa por IA'
                                : 'Valores registrados'}
                          </Badge>
                        </div>
                        {row.image_id && (
                          <Image
                            unoptimized
                            width={800}
                            height={600}
                            className="saved-food-image meal-photo"
                            src={`/api/food-images/${encodeURIComponent(row.image_id)}`}
                            alt={`Foto de ${row.meal}`}
                            loading="lazy"
                          />
                        )}
                        <p className="food-description">{excerpt(row.text)}</p>
                        {row.analysis && (
                          <p className="small muted">
                            {Object.keys(nutrients)
                              .map(
                                (key) =>
                                  `${nutrients[key]}: ${format(sum(row.analysis.items, key), 0)}${array(row.analysis.items).some((item) => item[key] == null) ? ' + pendente' : ''}`,
                              )
                              .join(' · ')}
                          </p>
                        )}
                        {row.analysis && (
                          <details className="method">
                            <summary>Alimentos e hipóteses</summary>
                            <FoodEstimate analysis={row.analysis} resetKey={row.id} />
                          </details>
                        )}
                        <div className="report-actions">
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() => edit(row)}
                          >
                            Editar
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() => edit(row, true)}
                          >
                            Copiar
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() =>
                              run(async () => {
                                const result = await personalApi(`food/${day}/remove`, {
                                  id: row.id,
                                  revision: diary.revision,
                                });
                                setDiary((value) => ({ ...value, ...result }));
                                setMessage('Refeição removida.');
                              })
                            }
                          >
                            Excluir
                          </Button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </PagedList>
            ) : (
              <p className="empty">Nenhuma refeição salva para este dia.</p>
            )}
          </section>
          <section className="panel">
            <h2>Cobertura do dia</h2>
            <p className="small muted">
              Declare completo quando todas as refeições estiverem registradas. Estimativas
              pendentes continuam identificadas.
            </p>
            {!diary.entries.length && (
              <Label className="checkbox-label" htmlFor="nutrition-fasting">
                <Checkbox
                  id="nutrition-fasting"
                  checked={fasting}
                  disabled={busy}
                  onCheckedChange={(checked) => setFasting(checked === true)}
                />
                Declaro que este dia não teve ingestão alimentar
              </Label>
            )}
            <div className="report-actions">
              <Button
                type="button"
                variant="default"
                className="primary"
                disabled={busy || (!diary.entries.length && !fasting)}
                onClick={() =>
                  run(async () => {
                    const result = await personalApi(`food/${day}/coverage`, {
                      completeness: 'complete',
                      fasting_declared: fasting,
                      revision: diary.revision,
                    });
                    setDiary((value) => ({ ...value, ...result }));
                    setMessage(
                      'Dia declarado completo. Valores pendentes continuam identificados.',
                    );
                  })
                }
              >
                Declarar dia completo
              </Button>
              {diary.completeness === 'complete' && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const result = await personalApi(`food/${day}/coverage`, {
                        completeness: diary.entries.length ? 'partial' : 'empty',
                        fasting_declared: false,
                        revision: diary.revision,
                      });
                      setDiary((value) => ({ ...value, ...result }));
                      setFasting(false);
                      setMessage('Diário reaberto.');
                    })
                  }
                >
                  Reabrir diário
                </Button>
              )}
            </div>
          </section>
          <details className="panel">
            <summary className="section-summary">Refeições frequentes e receitas</summary>
            <div className="recipe-library">
              {recipes.length ? (
                <PagedList items={recipes} resetKey="food-library" label="Receitas">
                  {(items) =>
                    items.map((recipe) => (
                      <div className="record-row" key={recipe.id}>
                        <div>
                          <strong>{recipe.title}</strong>
                          <p>{excerpt(recipe.text)}</p>
                          <span className="small muted">
                            {recipe.servings || 1} porção(ões) na receita
                          </span>
                          <Label className="recipe-portions">
                            Porções a consumir
                            <Input
                              type="number"
                              min="0.1"
                              max="1000"
                              step="0.1"
                              disabled={busy}
                              value={portions[recipe.id] ?? 1}
                              onChange={(e) =>
                                setPortions((v) => ({ ...v, [recipe.id]: e.target.value }))
                              }
                            />
                          </Label>
                        </div>
                        <div className="report-actions">
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() => prepareRecipe(recipe)}
                          >
                            Usar e revisar
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() =>
                              run(async () => {
                                await personalApi(
                                  `food-library/${encodeURIComponent(recipe.id)}/remove`,
                                  {},
                                );
                                await loadLibrary();
                                setMessage('Receita removida da biblioteca.');
                              })
                            }
                          >
                            Remover
                          </Button>
                        </div>
                      </div>
                    ))
                  }
                </PagedList>
              ) : (
                <p className="empty">
                  Abra uma refeição estimada para salvá-la como referência para as próximas vezes.
                </p>
              )}
            </div>
          </details>
          {editorOpen && (
            <Modal
              returnFocusRef={editorFocusRef}
              title={editing ? 'Editar refeição' : 'Adicionar refeição'}
              onClose={closeEditor}
              busy={busy || readingImage}
              dirty={dirty}
              className="meal-modal"
            >
              <ErrorNotice error={error} />
              <StatusNotice message={message} />
              <fieldset className="food-fieldset" disabled={busy || readingImage}>
                <div className="form-grid">
                  <Label>
                    Refeição
                    <NativeSelect
                      value={entry.meal}
                      onChange={(e) => input('meal', e.target.value)}
                    >
                      {meals.map((meal) => (
                        <option key={meal}>{meal}</option>
                      ))}
                    </NativeSelect>
                  </Label>
                  <Label>
                    Foto opcional
                    <Input
                      key={entry.id}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={(e) => imageSelected(e.target.files?.[0])}
                    />
                  </Label>
                  <Field className="wide">
                    <Label htmlFor={`${fieldPrefix}-meal-description`}>O que você comeu?</Label>
                    <Textarea
                      id={`${fieldPrefix}-meal-description`}
                      rows="4"
                      maxLength="10000"
                      value={entry.text}
                      onChange={(e) => input('text', e.target.value)}
                      placeholder="Ex.: 200 ml de iogurte, 1 scoop de whey e 1 banana. Informe quantidades e preparo."
                    />
                  </Field>
                </div>
                {readingImage && (
                  <p className="small muted" role="status">
                    Carregando a foto…
                  </p>
                )}
                {entry.image && (
                  <div className="food-image">
                    <Image
                      unoptimized
                      width={800}
                      height={600}
                      src={entry.image}
                      alt="Foto da refeição selecionada"
                    />
                    <div>
                      <p className="small muted">
                        A IA considera a foto e a descrição. Informe o peso quando conhecido.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() =>
                          setEntry((value) => ({
                            ...value,
                            image: null,
                            analysis: null,
                            save_token: newId(),
                          }))
                        }
                      >
                        Remover foto selecionada
                      </Button>
                    </div>
                  </div>
                )}
                {!entry.image && entry.image_id && (
                  <p className="small muted">A foto já cadastrada será mantida.</p>
                )}
                <div className="report-actions">
                  <Button
                    type="button"
                    variant="default"
                    className="primary"
                    disabled={!canSave || busy}
                    onClick={save}
                  >
                    {busy ? 'Salvando…' : editing ? 'Salvar alterações' : 'Salvar refeição'}
                  </Button>
                </div>
                {diary.configured && (
                  <p className="small muted">
                    {diary.local ? 'Ollama local · sem cobrança por chamada' : 'OpenAI · API paga'}{' '}
                    · {diary.model}. Ao salvar, a IA calcula e registra a estimativa.
                  </p>
                )}
                {busy && (
                  <p className="muted" role="status">
                    Concluindo a operação. A estimativa de uma refeição pode levar alguns instantes…
                  </p>
                )}
                {!diary.configured && (
                  <p className="small muted">
                    A refeição será salva com estimativa pendente. Configure a IA em Dados e fontes.
                  </p>
                )}
                {analysis && (
                  <details className="method">
                    <summary>Última estimativa</summary>
                    <FoodEstimate analysis={analysis} resetKey={entry.id} />
                    <p className="small muted">
                      Salvar recalcula os valores a partir da descrição e da foto.
                    </p>
                  </details>
                )}
                {analysis && (
                  <details className="method">
                    <summary>Salvar como refeição frequente</summary>
                    <div className="form-grid">
                      <Label>
                        Nome da refeição frequente
                        <Input
                          value={recipeTitle}
                          maxLength="200"
                          onChange={(e) => setRecipeTitle(e.target.value)}
                          placeholder="Ex.: café da manhã habitual"
                        />
                      </Label>
                      <Label>
                        Porções descritas
                        <Input
                          type="number"
                          min="1"
                          max="100"
                          value={servings}
                          onChange={(e) => setServings(Number(e.target.value))}
                        />
                      </Label>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={
                        busy ||
                        !recipeTitle.trim() ||
                        !entry.text.trim() ||
                        !Number.isFinite(servings) ||
                        servings < 1 ||
                        servings > 100 ||
                        !array(analysis.items).length ||
                        !analysis.items.every((item) => item.name.trim())
                      }
                      onClick={saveRecipe}
                    >
                      Salvar na biblioteca
                    </Button>
                    <p className="small muted">
                      A biblioteca guarda esta descrição e estimativa. Para registrar o consumo no
                      dia, use Salvar refeição.
                    </p>
                  </details>
                )}
              </fieldset>
            </Modal>
          )}
          {reviewOpen && (
            <Modal
              title="Análise do dia"
              onClose={() => setReviewOpen(false)}
              busy={reviewState.busy}
              dirty={reviewState.dirty}
            >
              <DayReview day={day} revision={diary.revision} onStateChange={setReviewState} />
            </Modal>
          )}
        </>
      )}
    </>
  );
}
