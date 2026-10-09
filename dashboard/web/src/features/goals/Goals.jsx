'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Field } from '@/components/ui/field';
import { NativeSelect } from '@/components/ui/native-select';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useId, useRef, useState } from 'react';
import { PagedList } from '@/components/shared/ui';
import {
  array,
  dayLabel,
  ErrorNotice,
  format,
  optionalNumber,
  PageHeading,
  personalApi,
  PersonalLoading,
  StatusNotice,
  today,
  usePersonal,
} from '@/lib/personalApi';

const types = {
  fat_loss: 'Reduzir gordura',
  weight_gain: 'Ganhar peso',
  maintenance: 'Manter composição',
  strength: 'Força',
  endurance: 'Resistência esportiva',
  sleep: 'Sono',
  consistency: 'Consistência',
  custom: 'Objetivo pessoal',
};
const metricUnits = {
  weight_kg: 'kg de peso',
  waist_cm: 'cm de cintura',
  body_fat_pct: '% de gordura corporal',
  weekly_sessions: 'sessões por semana',
  distance_km: 'km',
  sleep_hours: 'horas de sono',
};
const statuses = {
  active: 'Ativo',
  paused: 'Pausado',
  completed: 'Concluído',
  archived: 'Arquivado',
};
const fresh = () => ({
  description: '',
  type: 'fat_loss',
  priority: 1,
  status: 'active',
  target_metric: 'weight_kg',
  target_value: '',
  target_kcal: '',
  desired_weekly_change_kg: '',
  due_date: '',
  preserve: [],
  notes: '',
});
const blankPlan = (day) => ({
  goal_id: '',
  effective_from: day,
  next_review_date: '',
  target_kcal: '',
  protein_g: '',
  carbs_g: '',
  fat_g: '',
  reason: 'Referência informada pelo usuário.',
});
const evidenceNames = {
  food_complete_days: 'Dias alimentares completos',
  weight_measurements: 'Medidas de peso',
  weekly_change_kg: 'Variação semanal (kg)',
  avg_deficit_kcal: 'Déficit médio (kcal)',
  days: 'Dias analisados',
  balance_usable_days: 'Dias com balanço utilizável',
};

function Plan({ value }) {
  if (!value) return <p className="small muted">Não há plano vigente para esta referência.</p>;
  return (
    <div className="plan-summary">
      <strong>
        {value.target_kcal != null
          ? `${format(value.target_kcal, 0)} kcal por dia`
          : 'Sem meta calórica'}
      </strong>
      <span>
        {value.protein_g != null
          ? `Proteína: ${format(value.protein_g, 0)} g por dia`
          : 'Proteína ainda sem meta'}
      </span>
      <span>
        {value.carbs_g != null ? `Carboidratos: ${format(value.carbs_g, 0)} g por dia` : ''}
        {value.fat_g != null ? ` · Gorduras: ${format(value.fat_g, 0)} g por dia` : ''}
      </span>
      <span>
        Versão {value.version || 1} · vigência {dayLabel(value.effective_from)}
      </span>
      <span>Próxima revisão: {dayLabel(value.next_review_date)}</span>
      {(value.reason || array(value.limitations).length > 0) && (
        <details className="method">
          <summary>Justificativa e limitações</summary>
          {value.reason && <p>{value.reason}</p>}
          <PagedList items={array(value.limitations)} label="Limitações do plano">
            {(rows) =>
              rows.map((text, index) => (
                <p className="small muted" key={index}>
                  {text}
                </p>
              ))
            }
          </PagedList>
        </details>
      )}
    </div>
  );
}

function ManualPlan({ model, goals, day, disabled, onStateChange }) {
  const fieldPrefix = useId();
  const queryClient = useQueryClient();
  const [value, setValue] = useState(() => blankPlan(day));
  const [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const lock = useRef(false),
    activeGoals = goals.filter((goal) => goal.status === 'active');
  const goalId = value.goal_id || activeGoals[0]?.id || '';
  useEffect(() => {
    onStateChange?.({ busy, dirty });
  }, [busy, dirty, onStateChange]);
  const input = (key) => (event) => {
    setDirty(true);
    setValue((row) => ({ ...row, [key]: event.target.value }));
  };
  async function submit(event) {
    event.preventDefault();
    if (lock.current || disabled) return;
    lock.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const record = {
        ...value,
        goal_id: goalId,
        ...Object.fromEntries(
          ['target_kcal', 'protein_g', 'carbs_g', 'fat_g'].map((key) => [
            key,
            optionalNumber(value[key]),
          ]),
        ),
        method: 'user_declared',
        status: 'active',
      };
      if (!record.next_review_date) delete record.next_review_date;
      await model.save('plans', record);
      setDirty(false);
      setValue(blankPlan(day));
      queryClient.invalidateQueries({ queryKey: ['food'] });
      queryClient.invalidateQueries({ queryKey: ['nutrition-targets'] });
      queryClient.invalidateQueries({ queryKey: ['day-review'] });
      setMessage('Nova versão do plano registrada com a vigência escolhida.');
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <details className="panel">
      <summary className="section-summary">Registrar um plano ou orientação informada</summary>
      <p className="small muted">
        Use referências pessoais ou profissionais. As versões anteriores permanecem guardadas.
      </p>
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      <form className="personal-form" onSubmit={submit}>
        <fieldset disabled={busy || disabled} className="form-fieldset">
          <p>
            Objetivo selecionado:{' '}
            <strong>
              {activeGoals.find((goal) => goal.id === goalId)?.description ||
                'Nenhum objetivo ativo'}
            </strong>
          </p>
          <RadioGroup
            value={goalId}
            onValueChange={(goal_id) => {
              setDirty(true);
              setValue((row) => ({ ...row, goal_id }));
            }}
            disabled={busy || disabled}
          >
            <PagedList items={activeGoals} label="Objetivos para o plano">
              {(rows) => (
                <div className="record-list">
                  {rows.map((goal) => (
                    <Label
                      className="checkbox-label"
                      key={goal.id}
                      htmlFor={`manual-plan-goal-${goal.id}`}
                    >
                      <RadioGroupItem id={`manual-plan-goal-${goal.id}`} value={goal.id} />
                      {goal.description}
                    </Label>
                  ))}
                </div>
              )}
            </PagedList>
          </RadioGroup>
          <div className="form-grid">
            <Label>
              Início da vigência
              <Input
                type="date"
                value={value.effective_from}
                onChange={input('effective_from')}
                required
              />
            </Label>
            <Label>
              Próxima revisão
              <Input
                type="date"
                value={value.next_review_date}
                onChange={input('next_review_date')}
              />
            </Label>
            <Label>
              Meta energética (kcal/dia)
              <Input
                type="number"
                min="500"
                max="10000"
                value={value.target_kcal}
                onChange={input('target_kcal')}
              />
            </Label>
            {[
              ['protein_g', 'Proteína (g/dia)'],
              ['carbs_g', 'Carboidratos (g/dia)'],
              ['fat_g', 'Gorduras (g/dia)'],
            ].map(([key, label]) => (
              <Label key={key}>
                {label}
                <Input
                  type="number"
                  min="0"
                  max="1000"
                  step="1"
                  value={value[key]}
                  onChange={input(key)}
                />
              </Label>
            ))}
            <Field className="wide">
              <Label htmlFor={`${fieldPrefix}-plan-reason`}>Origem e motivo</Label>
              <Textarea
                id={`${fieldPrefix}-plan-reason`}
                required
                rows="2"
                maxLength="5000"
                value={value.reason}
                onChange={input('reason')}
              />
            </Field>
          </div>
        </fieldset>
        <Button
          type="submit"
          variant="default"
          className="primary"
          disabled={busy || disabled || model.loading || !goalId}
        >
          {busy ? 'Salvando…' : 'Registrar versão do plano'}
        </Button>
      </form>
    </details>
  );
}

export default function Goals({ initialDay, onStateChange }) {
  const fieldPrefix = useId();
  const queryClient = useQueryClient();
  const [day, setDay] = useState(initialDay || today()),
    model = usePersonal(day, 30);
  const [form, setForm] = useState(fresh),
    [showForm, setShowForm] = useState(false),
    [formDirty, setFormDirty] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [manualState, setManualState] = useState({ busy: false, dirty: false }),
    [goalFilter, setGoalFilter] = useState('current');
  const lock = useRef(false),
    formRef = useRef(null);
  const allGoals = array(model.state.goals)
    .slice()
    .sort((a, b) => (a.priority || 1) - (b.priority || 1));
  const goals = allGoals.filter(
    (goal) => goalFilter === 'all' || ['active', 'paused'].includes(goal.status),
  );
  const proposals = array(model.summary.proposals || model.state.proposals)
    .filter((proposal) => proposal.status === 'pending')
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const futurePlans = array(model.state.plans)
    .filter((plan) => plan.status === 'active' && plan.effective_from > day)
    .sort((a, b) => a.effective_from.localeCompare(b.effective_from));
  const saving = busy || manualState.busy,
    dirty = formDirty || manualState.dirty;
  const active = model.summary.active_plan,
    automatic = model.state?.preferences?.auto_nutrition_targets !== false,
    progress = model.summary.progress || {};
  const activeGoalId = model.summary.active_goal?.id,
    load = model.load;
  useEffect(() => {
    onStateChange?.({ busy: saving, dirty });
  }, [saving, dirty, onStateChange]);
  useEffect(() => {
    if (!automatic || !activeGoalId || saving) return;
    const timer = setInterval(() => load().catch(() => {}), 15000);
    return () => clearInterval(timer);
  }, [automatic, day, load, activeGoalId, saving]);
  const change = (key) => (event) => {
    setFormDirty(true);
    setForm((value) => ({ ...value, [key]: event.target.value }));
  };
  async function run(action, notice) {
    if (lock.current || manualState.busy) return false;
    lock.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
      await model.load();
      queryClient.invalidateQueries({ queryKey: ['food'] });
      queryClient.invalidateQueries({ queryKey: ['nutrition-targets'] });
      queryClient.invalidateQueries({ queryKey: ['day-review'] });
      if (notice) setMessage(notice);
      return true;
    } catch (e) {
      setError(e.message);
      if (e.status === 409) await model.load().catch(() => {});
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function closeForm() {
    if (saving) return false;
    if (formDirty && !window.confirm('Descartar as alterações não salvas do objetivo?'))
      return false;
    setForm(fresh());
    setFormDirty(false);
    setShowForm(false);
    return true;
  }
  function createGoal() {
    if (!closeForm()) return;
    setForm(fresh());
    setShowForm(true);
  }
  function editGoal(goal) {
    if (!closeForm()) return;
    setForm({ ...fresh(), ...goal });
    setShowForm(true);
    requestAnimationFrame(() =>
      formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    );
  }
  async function submit(event) {
    event.preventDefault();
    const saved = await run(
      () =>
        model.save('goals', {
          ...form,
          priority: Number(form.priority),
          ...Object.fromEntries(
            ['target_value', 'target_kcal', 'desired_weekly_change_kg'].map((key) => [
              key,
              optionalNumber(form[key]),
            ]),
          ),
          preserve: array(form.preserve)
            .map((value) => value.trim())
            .filter(Boolean),
          due_date: form.due_date || null,
        }),
      'Objetivo salvo. A meta foi atualizada quando havia dados suficientes.',
    );
    if (saved) {
      setForm(fresh());
      setFormDirty(false);
      setShowForm(false);
    }
  }
  return (
    <>
      <PageHeading kicker="OBJETIVOS / PLANO" title="Seus objetivos">
        Consulte as metas e ajuste o que deseja alcançar.
      </PageHeading>
      <div className="filters">
        <Label>
          Dia de referência
          <Input
            type="date"
            disabled={saving || dirty}
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
        </Label>
        <Button
          type="button"
          variant="default"
          className="primary"
          disabled={saving || model.loading}
          onClick={() =>
            run(
              () => personalApi('personal/review', { day }),
              'Revisão concluída. Confira as propostas disponíveis.',
            )
          }
        >
          {busy ? 'Processando…' : 'Revisar progresso'}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={saving}
          onClick={() => (showForm ? closeForm() : createGoal())}
        >
          {showForm ? 'Fechar formulário' : 'Criar objetivo'}
        </Button>
      </div>
      <PersonalLoading model={model} />
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      {model.value && (
        <>
          {showForm && (
            <section className="panel" ref={formRef}>
              <h2>{form.id ? 'Editar objetivo' : 'Novo objetivo'}</h2>
              <form className="personal-form" onSubmit={submit}>
                <fieldset disabled={saving} className="form-fieldset">
                  <div className="form-grid">
                    <Label className="wide">
                      Descrição
                      <Input
                        required
                        maxLength="1000"
                        value={form.description}
                        onChange={change('description')}
                        placeholder="Ex.: reduzir gordura preservando força e disposição"
                      />
                    </Label>
                    <Label>
                      Tipo
                      <NativeSelect value={form.type} onChange={change('type')}>
                        {Object.entries(types).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </NativeSelect>
                    </Label>
                    <Label>
                      Prioridade · 1 é a principal
                      <Input
                        type="number"
                        min="1"
                        max="20"
                        value={form.priority}
                        onChange={change('priority')}
                      />
                    </Label>
                    <Label>
                      Indicador
                      <NativeSelect
                        value={form.target_metric || ''}
                        onChange={change('target_metric')}
                      >
                        <option value="">Sem indicador numérico</option>
                        <option value="weight_kg">Peso (kg)</option>
                        <option value="waist_cm">Cintura (cm)</option>
                        <option value="body_fat_pct">Gordura corporal (%)</option>
                        <option value="weekly_sessions">Sessões por semana</option>
                        <option value="distance_km">Distância (km)</option>
                        <option value="sleep_hours">Sono (horas)</option>
                      </NativeSelect>
                    </Label>
                    <Label>
                      Valor desejado
                      <Input
                        type="number"
                        min="0"
                        step="0.1"
                        value={form.target_value ?? ''}
                        onChange={change('target_value')}
                      />
                    </Label>
                    <Label>
                      Data desejada
                      <Input
                        type="date"
                        value={form.due_date || ''}
                        onChange={change('due_date')}
                      />
                    </Label>
                    <Label>
                      Meta energética informada (kcal)
                      <Input
                        type="number"
                        min="500"
                        max="10000"
                        value={form.target_kcal ?? ''}
                        onChange={change('target_kcal')}
                      />
                    </Label>
                    <Label>
                      Variação semanal desejada (kg)
                      <Input
                        type="number"
                        min="-0.5"
                        max="0.5"
                        step="0.05"
                        value={form.desired_weekly_change_kg ?? ''}
                        onChange={change('desired_weekly_change_kg')}
                        placeholder="Negativo para perda"
                      />
                    </Label>
                    <Label>
                      Estado
                      <NativeSelect value={form.status} onChange={change('status')}>
                        {Object.entries(statuses).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </NativeSelect>
                    </Label>
                    <Label className="wide">
                      O que preservar? Separar por vírgula
                      <Input
                        value={array(form.preserve).join(', ')}
                        onChange={(e) => {
                          setFormDirty(true);
                          setForm((value) => ({
                            ...value,
                            preserve: e.target.value.split(',').map((item) => item.trim()),
                          }));
                        }}
                        placeholder="Força, desempenho, recuperação…"
                      />
                    </Label>
                    <Field className="wide">
                      <Label htmlFor={`${fieldPrefix}-goal-notes`}>Notas</Label>
                      <Textarea
                        id={`${fieldPrefix}-goal-notes`}
                        rows="3"
                        value={form.notes || ''}
                        onChange={change('notes')}
                      />
                    </Field>
                  </div>
                </fieldset>
                <div className="report-actions">
                  <Button
                    type="submit"
                    variant="default"
                    className="primary"
                    disabled={saving || model.loading}
                  >
                    Salvar objetivo
                  </Button>
                  <Button type="button" variant="outline" disabled={saving} onClick={closeForm}>
                    Cancelar
                  </Button>
                </div>
              </form>
            </section>
          )}
          <div className="split">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Plano vigente</h2>
                  <p>Metas para {dayLabel(day)}.</p>
                </div>
                {active?.status && (
                  <Badge variant={active.status === 'active' ? 'default' : 'secondary'}>
                    {active.status === 'active'
                      ? 'Ativo'
                      : active.status === 'provisional'
                        ? 'Provisório'
                        : active.status}
                  </Badge>
                )}
              </div>
              <Plan value={active} />
            </section>
            <section className="panel">
              <h2>Progresso observado</h2>
              <div className="context-grid">
                <div>
                  <span>Medidas de peso no período</span>
                  <b>{progress.weight_measurements ?? 0}</b>
                </div>
                <div>
                  <span>Variação observada</span>
                  <b>
                    {progress.weight_change_kg != null
                      ? `${format(progress.weight_change_kg, 2)} kg`
                      : 'Sem dado'}
                  </b>
                </div>
                <div>
                  <span>Variação por semana</span>
                  <b>
                    {progress.weekly_change_kg != null
                      ? `${format(progress.weekly_change_kg, 2)} kg`
                      : 'Sem dado'}
                  </b>
                </div>
                <div>
                  <span>Dias com alimentação completa</span>
                  <b>{model.summary.coverage?.food_complete_days ?? 0}</b>
                </div>
              </div>
              <p className="small muted">Uma mudança isolada não sustenta um ajuste.</p>
            </section>
          </div>
          <section className="panel">
            <h2>Meta alimentar automática</h2>
            <Label className="checkbox-label" htmlFor="goals-automatic-targets">
              <Checkbox
                id="goals-automatic-targets"
                checked={automatic}
                disabled={saving || model.loading}
                onCheckedChange={(checked) =>
                  run(
                    () =>
                      model.save('preferences', {
                        ...model.state.preferences,
                        auto_nutrition_targets: checked === true,
                      }),
                    checked === true
                      ? 'Atualização automática ativada.'
                      : 'Atualização automática pausada.',
                  )
                }
              />
              Usar IA local para atualizar as metas diariamente
            </Label>
            <p className="small muted">
              Perfil, objetivos e treinos orientam a meta. Falhas preservam a última referência.
            </p>
            {model.value.nutrition_targets?.message && (
              <p className="small muted" role="status">
                {model.value.nutrition_targets.message}
              </p>
            )}
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Seus objetivos</h2>
              <Label>
                Exibir
                <NativeSelect value={goalFilter} onChange={(e) => setGoalFilter(e.target.value)}>
                  <option value="current">Ativos e pausados</option>
                  <option value="all">Todos os estados</option>
                </NativeSelect>
              </Label>
            </div>
            <PagedList items={goals} resetKey={goalFilter} label="Objetivos">
              {(rows) =>
                rows.length ? (
                  rows.map((goal) => (
                    <div className="record-row" key={goal.id}>
                      <div>
                        <Badge variant={goal.status === 'active' ? 'default' : 'secondary'}>
                          {statuses[goal.status] || goal.status}
                        </Badge>
                        <h3>{goal.description}</h3>
                        <p>
                          {types[goal.type] || goal.type} · prioridade {goal.priority || 1}
                          {goal.target_value != null
                            ? ` · alvo ${format(goal.target_value)} ${metricUnits[goal.target_metric] || 'no indicador definido'}`
                            : ''}
                          {goal.due_date ? ` · ${dayLabel(goal.due_date)}` : ''}
                        </p>
                        {array(goal.preserve).length > 0 && (
                          <p className="small muted">Preservar: {goal.preserve.join(', ')}</p>
                        )}
                      </div>
                      <div className="report-actions">
                        <Button
                          type="button"
                          variant="outline"
                          disabled={saving}
                          onClick={() => editGoal(goal)}
                        >
                          Editar
                        </Button>
                        {goal.status === 'active' && (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={saving || model.loading}
                            onClick={() =>
                              run(
                                () => model.save('goals', { ...goal, status: 'paused' }),
                                'Objetivo pausado.',
                              )
                            }
                          >
                            Pausar
                          </Button>
                        )}
                        {goal.status === 'paused' && (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={saving || model.loading}
                            onClick={() =>
                              run(
                                () => model.save('goals', { ...goal, status: 'active' }),
                                'Objetivo retomado.',
                              )
                            }
                          >
                            Retomar
                          </Button>
                        )}
                        {['active', 'paused'].includes(goal.status) && (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={saving || model.loading}
                            onClick={() =>
                              run(
                                () => model.save('goals', { ...goal, status: 'completed' }),
                                'Objetivo concluído.',
                              )
                            }
                          >
                            Concluir
                          </Button>
                        )}
                        {goal.status !== 'archived' && (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={saving || model.loading}
                            onClick={() =>
                              run(
                                () => model.save('goals', { ...goal, status: 'archived' }),
                                'Objetivo arquivado.',
                              )
                            }
                          >
                            Arquivar
                          </Button>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    <p>Nenhum objetivo neste filtro.</p>
                    <Button type="button" variant="outline" disabled={saving} onClick={createGoal}>
                      Criar objetivo
                    </Button>
                  </div>
                )
              }
            </PagedList>
          </section>
          {proposals.length > 0 && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Propostas disponíveis</h2>
                  <p>Confira a evidência antes de aceitar uma mudança.</p>
                </div>
              </div>
              <PagedList items={proposals} resetKey={day} label="Propostas disponíveis">
                {(rows) =>
                  rows.map((proposal) => (
                    <article className="proposal-card" key={proposal.id}>
                      <h3>
                        {proposal.action === 'adjust'
                          ? 'Ajustar o plano'
                          : proposal.action === 'collect_data'
                            ? 'Registrar mais dados'
                            : 'Manter o plano'}
                      </h3>
                      <p>{proposal.reason}</p>
                      {proposal.suggested_plan && <Plan value={proposal.suggested_plan} />}
                      <details className="method">
                        <summary>Ver evidência e limitações</summary>
                        <PagedList
                          items={Object.entries(proposal.evidence || {})}
                          label="Evidências"
                        >
                          {(evidence) => (
                            <div className="evidence-grid">
                              {evidence.map(([key, value]) => (
                                <p key={key}>
                                  <span>{evidenceNames[key] || key.replaceAll('_', ' ')}</span>
                                  <strong>
                                    {typeof value === 'object'
                                      ? JSON.stringify(value)
                                      : String(value ?? 'Sem dado')}
                                  </strong>
                                </p>
                              ))}
                            </div>
                          )}
                        </PagedList>
                        <PagedList
                          items={array(proposal.limitations)}
                          label="Limitações da proposta"
                        >
                          {(limitations) =>
                            limitations.map((text, index) => <p key={index}>{text}</p>)
                          }
                        </PagedList>
                      </details>
                      <div className="report-actions">
                        <Button
                          type="button"
                          variant="default"
                          className="primary"
                          disabled={saving || model.loading}
                          onClick={() =>
                            run(
                              () =>
                                personalApi(
                                  `personal/proposals/${encodeURIComponent(proposal.id)}/decision`,
                                  { decision: 'accepted', day },
                                ),
                              'Proposta aceita. Confira a vigência do plano.',
                            )
                          }
                        >
                          Aceitar proposta
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={saving || model.loading}
                          onClick={() =>
                            run(
                              () =>
                                personalApi(
                                  `personal/proposals/${encodeURIComponent(proposal.id)}/decision`,
                                  { decision: 'rejected', day },
                                ),
                              'Proposta rejeitada. O plano foi preservado.',
                            )
                          }
                        >
                          Rejeitar
                        </Button>
                      </div>
                    </article>
                  ))
                }
              </PagedList>
            </section>
          )}
          {futurePlans.length > 0 && (
            <details className="panel">
              <summary className="section-summary">Planos com vigência futura</summary>
              <PagedList items={futurePlans} resetKey={day} label="Planos futuros">
                {(rows) => rows.map((plan) => <Plan key={plan.id} value={plan} />)}
              </PagedList>
            </details>
          )}
          <ManualPlan
            key={day}
            model={model}
            goals={allGoals}
            day={day}
            disabled={busy}
            onStateChange={setManualState}
          />
        </>
      )}
    </>
  );
}
