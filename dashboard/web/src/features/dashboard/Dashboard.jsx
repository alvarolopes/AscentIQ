'use client';
import { useState } from 'react';
import {
  array,
  dayLabel,
  ErrorNotice,
  format,
  personalApi,
  PersonalLoading,
  today,
  usePersonal,
} from '@/lib/personalApi';
import { InfoButton, Modal, PagedList } from '@/components/shared/ui';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FieldLabel } from '@/components/ui/field';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { useQuery } from '@tanstack/react-query';
import DayReview from '@/features/analyses/DayReview';
import Frequency from '@/features/dashboard/Frequency';
import CheckinForm from '@/features/checkins/CheckinForm';
const intakeStatus = {
  none: 'Sem registros',
  empty: 'Sem registros',
  partial: 'Diário parcial',
  complete: 'Dia completo',
  pending: 'Calorias pendentes',
};
const coverageNames = {
  full: 'Completa',
  complete: 'Completa',
  partial: 'Parcial',
  unknown: 'Desconhecida',
};
const sourceNames = {
  profile_model: 'Modelo a partir do perfil',
  profile_declared: 'Referência diária informada',
  manual: 'Registro manual',
  garmin: 'Garmin Connect',
  garmin_daily: 'Garmin · sinais diários',
  wearable: 'Relógio ou plataforma',
  unknown: 'Fonte desconhecida',
};
const methodNames = {
  personal_energy_mifflin_v1: 'Equação de Mifflin com fator de atividade',
  declared_profile_daily_total_v1: 'Total diário informado no perfil',
  daily_total_v1: 'Total diário da fonte',
  declared_daily_total_v1: 'Total diário informado',
};
const sourceLabel = (value) => sourceNames[value] || value || 'Sem fonte';
const methodLabel = (value) =>
  methodNames[value] || (value ? 'Método informado pela fonte' : 'Sem método');
function Section({ title, children, description }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
function SummaryCard({ title, value, note, onClick, action }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="metric-value">{value}</div>
        <p className="text-xs text-muted-foreground">{note}</p>
        {onClick && (
          <Button variant="outline" onClick={onClick}>
            {action}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function EnergyEvidence({ energy }) {
  const basis = {
    modeled_full_day: 'Dia completo estimado pelo modelo',
    source_declared_full: 'Dia completo declarado pela fonte',
    source_partial_or_unknown: 'Observação parcial ou cobertura desconhecida',
  };
  return (
    <>
      <p>
        {methodLabel(energy.method)} · {sourceLabel(energy.source)}.{' '}
        {basis[energy.coverage_basis] || 'Cobertura ainda não informada'}.
      </p>
      <div className="evidence-grid">
        {[
          ['total_kcal', 'Total diário (kcal)'],
          ['resting_kcal', 'Repouso (kcal)'],
          ['active_kcal', 'Atividade (kcal)'],
          ['exercise_kcal', 'Exercício (kcal)'],
        ].map(([key, label]) => (
          <p key={key}>
            <span>{label}</span>
            <strong>{format(energy.components?.[key], 0)}</strong>
          </p>
        ))}
      </div>
      <p>Exercícios da mesma fonte já incluídos no total não são somados novamente.</p>
      {array(energy.alternatives).length > 0 && (
        <>
          <h3>Outras referências preservadas</h3>
          <PagedList items={array(energy.alternatives)} label="Referências de gasto">
            {(rows) => (
              <div
                className="table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Registros em tabela"
              >
                <table>
                  <thead>
                    <tr>
                      <th>Origem</th>
                      <th>Gasto (kcal)</th>
                      <th>Cobertura</th>
                      <th>Horas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={row.id || index}>
                        <td>{sourceLabel(row.source)}</td>
                        <td>{format(row.total_kcal, 0)}</td>
                        <td>{coverageNames[row.coverage] || 'Desconhecida'}</td>
                        <td>{format(row.coverage_hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </PagedList>
          <p>São referências alternativas; não compõem uma soma com o gasto selecionado.</p>
        </>
      )}
    </>
  );
}

export default function Dashboard({ data, onNavigate, onAssistant, initialDay }) {
  const [day, setDay] = useState(initialDay || today()),
    model = usePersonal(day, 14);
  const foodQuery = useQuery({
    queryKey: ['food', day],
    queryFn: ({ signal }) => personalApi(`food/${day}`, undefined, signal),
  });
  const food = foodQuery.data || null,
    foodError = foodQuery.error?.message || '';
  const [dialog, setDialog] = useState(null);
  const [dialogState, setDialogState] = useState({ busy: false, dirty: false });
  const energy = model.summary.energy || {},
    activePlan = model.summary.active_plan,
    goal = model.summary.active_goal;
  const strength = array(data?.strength).filter((row) => row.date === day);
  const linked = new Set(strength.flatMap((row) => array(row.garmin_activity_ids).map(String)));
  const sessions = [
    ...array(data?.activities).filter((row) => row.date === day && !linked.has(String(row.id))),
    ...strength,
  ];
  const sleep = array(data?.sleep?.daily).find((row) => row.date === day);
  const checkin = array(model.state.checkins).find((row) => row.date === day);
  const trainingMinutes = sessions.reduce(
    (sum, row) => sum + Number(row.duration_seconds ?? 0) / 60,
    0,
  );
  const trainingLoad = array(data?.performance?.series).find((row) => row.date === day)?.daily_load;
  const trainingNote = `${trainingLoad != null ? `Carga registrada: ${format(trainingLoad)}.` : 'Carga ainda sem dado.'}${trainingMinutes ? ` ${format(trainingMinutes, 0)} minutos com duração disponível.` : ''}`;

  const kcalTarget = food?.targets?.kcal ?? activePlan?.target_kcal;
  const proteinTarget = food?.targets?.protein_g ?? activePlan?.protein_g;
  const proteinKnown =
    food?.fasting_declared ||
    array(food?.entries).some((entry) =>
      array(entry.analysis?.items).some((item) => item.protein_g != null),
    );
  const caloriesKnown =
    food?.fasting_declared ||
    array(food?.entries).some((entry) =>
      array(entry.analysis?.items).some((item) => item.kcal != null),
    );
  const protein = proteinKnown ? food?.totals?.protein_g : null;
  const registered = caloriesKnown ? (food?.totals?.kcal ?? energy.registered_kcal) : null;
  const open = (value) => {
    setDialogState({ busy: false, dirty: false });
    setDialog(value);
  };
  const navigate = (tab) => onNavigate?.(tab, day);
  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Dashboard</h2>
            <p>Alimentação, treinos e recuperação</p>
          </div>
        </div>
        <div className="filters">
          <FieldLabel>
            Dia
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </FieldLabel>
          <Button disabled={model.loading} onClick={() => model.load().catch(() => {})}>
            Atualizar
          </Button>
          <InfoButton title="Como ler este dia">
            <p>
              O total registrado pode ser apenas um subtotal. Um diário parcial ou com calorias
              pendentes não permite afirmar o déficit do dia.
            </p>
            <PagedList items={array(energy.limitations)} label="Limitações dos registros">
              {(rows) => rows.map((text, index) => <p key={index}>{text}</p>)}
            </PagedList>
            <p>
              Sem atividade registrada não confirma descanso. O sono mantém a data atribuída pela
              fonte.
            </p>
            <h3>Referência energética</h3>
            <EnergyEvidence energy={energy} />
          </InfoButton>
        </div>
      </section>
      <PersonalLoading model={model} />
      <ErrorNotice error={foodError} />
      {model.value && (
        <>
          <div className="report-actions dashboard-actions">
            <Button className="primary" onClick={() => open('review')}>
              Analisar meu dia
            </Button>
            <Button onClick={() => open('checkin')}>
              {checkin ? 'Editar check-in' : 'Registrar check-in'}
            </Button>
            <Button onClick={() => navigate('goals')}>Objetivos</Button>
            <Button onClick={() => (onAssistant ? onAssistant(day) : navigate('assistant'))}>
              Assistente
            </Button>
          </div>
          <div className="split dashboard-summary">
            <SummaryCard
              title="Alimentação"
              value={
                <>
                  {format(registered, 0)}{' '}
                  <small>/ {kcalTarget != null ? format(kcalTarget, 0) : 'Sem meta'} kcal</small>
                </>
              }
              note={`${intakeStatus[energy.intake_status] || 'Sem registros'}${energy.pending_count ? ` · ${energy.pending_count} estimativa(s) pendente(s)` : ''}`}
              onClick={() => navigate('nutrition')}
              action="Ver Nutrition"
            />
            <SummaryCard
              title="Proteína"
              value={
                <>
                  {format(protein, 0)}{' '}
                  <small>/ {proteinTarget != null ? format(proteinTarget, 0) : 'Sem meta'} g</small>
                </>
              }
              note={
                proteinKnown
                  ? 'Total das estimativas disponíveis.'
                  : 'Ainda sem proteína estimada neste dia.'
              }
            />
            <SummaryCard
              title="Treino"
              value={
                <>
                  {sessions.length} <small>atividade(s)</small>
                </>
              }
              note={trainingNote}
              onClick={() => navigate('overview')}
              action="Ver Workouts"
            />
            <SummaryCard
              title="Sono"
              value={
                sleep?.duration_minutes != null ? (
                  <>
                    {format(sleep.duration_minutes / 60, 1)} <small>h</small>
                  </>
                ) : (
                  'Sem dado'
                )
              }
              note={
                sleep
                  ? `Referência: ${dayLabel(sleep.date)}${sleep.score != null ? ` · pontuação ${format(sleep.score, 0)}` : ''}`
                  : `Nenhum registro para ${dayLabel(day)}.`
              }
              onClick={() => navigate('sleep')}
              action="Ver Sleep"
            />
          </div>
          <div className="split">
            <Section title="Objetivo principal">
              <h3>{goal?.description || 'Você ainda não definiu um objetivo.'}</h3>
              <p className="small muted">
                {activePlan
                  ? `Plano ${activePlan.version || 1} · próxima revisão ${dayLabel(activePlan.next_review_date)}`
                  : 'Defina um objetivo para acompanhar seu progresso.'}
              </p>
              <Button onClick={() => navigate('goals')}>Abrir objetivos e plano</Button>
            </Section>
            <Section title="Check-in">
              <p>
                {checkin
                  ? 'Seu contexto de recuperação está registrado.'
                  : 'Sem check-in para este dia.'}
              </p>
              <p className="small muted">
                Fadiga, disposição, fome e sono ajudam a interpretar seus registros.
              </p>
              <Button onClick={() => open('checkin')}>
                {checkin ? 'Editar check-in' : 'Registrar check-in'}
              </Button>
            </Section>
          </div>
          {model.value.nutrition_targets?.status === 'missing_data' && (
            <div className="notice">
              <strong>Complete seu perfil para calcular a meta</strong>
              <p>{model.value.nutrition_targets.message}</p>
              <Button onClick={() => navigate('profile')}>Perfil e medidas</Button>
            </div>
          )}
          <Frequency revision={`${model.state.revision}-${data.generated_at}`} />
        </>
      )}
      {dialog === 'review' && (
        <Modal
          title={`Análise do dia · ${dayLabel(day)}`}
          onClose={() => setDialog(null)}
          busy={dialogState.busy}
          dirty={dialogState.dirty}
        >
          <DayReview day={day} revision={model.state.revision} onStateChange={setDialogState} />
        </Modal>
      )}
      {dialog === 'checkin' && (
        <Modal
          title={`Check-in · ${dayLabel(day)}`}
          onClose={() => setDialog(null)}
          busy={dialogState.busy}
          dirty={dialogState.dirty}
        >
          <CheckinForm
            day={day}
            model={model}
            onStateChange={setDialogState}
            onSaved={() => setDialog(null)}
          />
        </Modal>
      )}
    </>
  );
}
