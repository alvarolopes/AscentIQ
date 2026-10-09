'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { NativeSelect } from '@/components/ui/native-select';
import { Card } from '@/components/ui/card';
import { useEffect, useId, useRef, useState } from 'react';
import { Modal, PagedList } from '@/components/shared/ui';
import { Chart as DefaultChart } from '@/components/shared/charts';
import CheckinForm from '@/features/checkins/CheckinForm';
import {
  array,
  dayLabel,
  ErrorNotice,
  format,
  optionalNumber,
  PageHeading,
  PersonalLoading,
  StatusNotice,
  today,
  usePersonal,
} from '@/lib/personalApi';

const numeric = ['height_cm', 'weight_kg', 'manual_tdee_kcal'];
const defaults = {
  review_days: 14,
  review_frequency_days: 7,
  min_complete_days: 10,
  min_weight_measurements: 4,
  adjustment_kcal: 100,
  review_reminders: true,
  energy_method: 'auto',
};
const blankMeasure = (day) => ({
  date: day,
  weight_kg: '',
  waist_cm: '',
  body_fat_pct: '',
  lean_mass_kg: '',
  method: 'manual',
  notes: '',
});
const blankEnergy = () => ({
  total_kcal: '',
  active_kcal: '',
  exercise_kcal: '',
  resting_kcal: '',
  source: 'manual',
  coverage: 'full',
  coverage_hours: 24,
  method: 'daily_total_v1',
});
function Section({ title, children, description }) {
  return (
    <Card className="panel gap-0">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}

export default function Health({ Chart = DefaultChart, initialDay = '', onStateChange }) {
  const [resolvedDay, setResolvedDay] = useState(initialDay);
  useEffect(() => {
    if (!resolvedDay) setResolvedDay(today());
  }, [resolvedDay]);
  if (!resolvedDay)
    return (
      <p className="muted" role="status">
        Preparando seu perfil…
      </p>
    );
  return <ProfileEditor Chart={Chart} initialDay={resolvedDay} onStateChange={onStateChange} />;
}

export function EnergyEditor({ day, model, onStateChange }) {
  const [record, setRecord] = useState(blankEnergy),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const lock = useRef(false);
  useEffect(() => {
    if (dirty) return;
    const saved = array(model.state.energy_records).find((row) => row.date === day);
    setRecord(
      saved
        ? {
            ...blankEnergy(),
            ...saved,
            ...Object.fromEntries(
              ['total_kcal', 'active_kcal', 'exercise_kcal', 'resting_kcal'].map((key) => [
                key,
                saved[key] ?? '',
              ]),
            ),
          }
        : blankEnergy(),
    );
  }, [day, dirty, model.state.energy_records]);
  useEffect(() => {
    onStateChange?.({ busy, dirty });
  }, [busy, dirty, onStateChange]);
  const input = (key) => (event) => {
    setDirty(true);
    setRecord((value) => ({ ...value, [key]: event.target.value }));
  };
  async function save(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      await model.save('energy_records', {
        ...record,
        date: day,
        ...Object.fromEntries(
          ['total_kcal', 'active_kcal', 'exercise_kcal', 'resting_kcal', 'coverage_hours'].map(
            (key) => [key, optionalNumber(record[key])],
          ),
        ),
      });
      setDirty(false);
      window.dispatchEvent(new Event('ascentiq-personal-changed'));
      setMessage('Gasto registrado. O balanço foi recalculado.');
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <details className="panel">
      <summary className="section-summary">Registrar uma referência de gasto energético</summary>
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      <p className="small muted">
        Referência de {dayLabel(day)}. O total diário já inclui os exercícios da fonte.
      </p>
      <form className="personal-form" onSubmit={save}>
        <fieldset disabled={busy} className="form-fieldset">
          <div className="form-grid">
            {[
              ['total_kcal', 'Total diário (kcal)'],
              ['resting_kcal', 'Repouso, se conhecido (kcal)'],
              ['active_kcal', 'Atividade, se conhecida (kcal)'],
              ['exercise_kcal', 'Exercício, se conhecido (kcal)'],
            ].map(([key, label]) => (
              <Label className="items-stretch" key={key}>
                {label}
                <Input
                  type="number"
                  min="0"
                  max="20000"
                  required={key === 'total_kcal'}
                  step="1"
                  value={record[key]}
                  onChange={input(key)}
                />
              </Label>
            ))}
            <Label className="items-stretch">
              Fonte
              <Input value={record.source} required onChange={input('source')} />
            </Label>
            <Label className="items-stretch">
              Cobertura
              <NativeSelect
                className="w-full min-w-0"
                value={record.coverage}
                onChange={input('coverage')}
              >
                <option value="full">Dia completo</option>
                <option value="partial">Parcial</option>
                <option value="unknown">Desconhecida</option>
              </NativeSelect>
            </Label>
            <Label className="items-stretch">
              Horas cobertas
              <Input
                type="number"
                min="0"
                max="24"
                value={record.coverage_hours ?? ''}
                onChange={input('coverage_hours')}
              />
            </Label>
            <Label className="items-stretch">
              Como o total foi obtido?
              <Input value={record.method || ''} onChange={input('method')} />
            </Label>
          </div>
        </fieldset>
        <Button variant="default" className="primary" disabled={busy || model.loading}>
          {busy ? 'Salvando…' : 'Salvar gasto'}
        </Button>
      </form>
    </details>
  );
}

function ProfileEditor({ Chart, initialDay, onStateChange }) {
  const fieldId = useId();
  const [day, setDay] = useState(initialDay),
    model = usePersonal(day, 30);
  const [profile, setProfile] = useState({}),
    [preferences, setPreferences] = useState({}),
    [measure, setMeasure] = useState(() => blankMeasure(day));
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [profileDirty, setProfileDirty] = useState(false),
    [preferencesDirty, setPreferencesDirty] = useState(false),
    [measureDirty, setMeasureDirty] = useState(false);
  const [checkinOpen, setCheckinOpen] = useState(false),
    [checkinState, setCheckinState] = useState({ busy: false, dirty: false }),
    [energyState, setEnergyState] = useState({ busy: false, dirty: false });
  const lock = useRef(false);
  const dirty =
    profileDirty || preferencesDirty || measureDirty || checkinState.dirty || energyState.dirty;
  const saving = busy || checkinState.busy || energyState.busy || model.loading;
  useEffect(() => {
    if (!model.value) return;
    if (!profileDirty) setProfile({ ...model.summary.profile, ...model.state.profile });
    if (!preferencesDirty) setPreferences({ ...defaults, ...model.state.preferences });
  }, [
    model.value,
    model.state.profile,
    model.state.preferences,
    model.summary.profile,
    profileDirty,
    preferencesDirty,
  ]);
  useEffect(() => {
    onStateChange?.({ busy: saving, dirty });
  }, [saving, dirty, onStateChange]);
  const input = (set, key, mark) => (event) => {
    mark?.();
    set((value) => ({ ...value, [key]: event.target.value }));
  };
  const markProfile = () => {
    setProfileDirty(true);
  };
  const markPreferences = () => {
    setPreferencesDirty(true);
  };
  const markMeasure = () => setMeasureDirty(true);
  async function commit(kind, value, notice, remove = false) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (kind === 'preferences')
        value = Object.fromEntries(Object.entries(value).filter(([, v]) => v !== null));
      await model.save(kind, value, remove);
      if (kind === 'profile') {
        setProfileDirty(false);
      }
      if (kind === 'preferences') {
        setPreferencesDirty(false);
      }
      window.dispatchEvent(new Event('ascentiq-personal-changed'));
      setMessage(notice);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function saveProfile(event) {
    event.preventDefault();
    commit(
      'profile',
      {
        ...profile,
        ...Object.fromEntries(numeric.map((key) => [key, optionalNumber(profile[key])])),
      },
      'Perfil atualizado.',
    );
  }
  async function saveMeasure(event) {
    event.preventDefault();
    const saved = await commit(
      'measurements',
      {
        ...measure,
        ...Object.fromEntries(
          ['weight_kg', 'waist_cm', 'body_fat_pct', 'lean_mass_kg'].map((key) => [
            key,
            optionalNumber(measure[key]),
          ]),
        ),
      },
      'Medida salva.',
    );
    if (saved) {
      setMeasure(blankMeasure(day));
      setMeasureDirty(false);
    }
  }
  function editMeasure(row) {
    if (measureDirty && !window.confirm('Descartar a medida não salva para editar este registro?'))
      return;
    setMeasure({
      ...row,
      ...Object.fromEntries(
        ['weight_kg', 'waist_cm', 'body_fat_pct', 'lean_mass_kg'].map((key) => [
          key,
          row[key] ?? '',
        ]),
      ),
    });
    setMeasureDirty(false);
  }
  const measures = array(model.state.measurements)
    .slice()
    .sort((a, b) => b.date.localeCompare(a.date));
  return (
    <>
      <PageHeading kicker="PERFIL / MEDIDAS" title="Suas referências pessoais">
        Mantenha o peso, o perfil e suas preferências atualizados.
      </PageHeading>
      <PersonalLoading model={model} />
      <ErrorNotice error={error} />
      <StatusNotice message={message} />
      {model.value && (
        <>
          <Section title="Perfil pessoal" description="Informações necessárias para os cálculos.">
            <form className="personal-form" onSubmit={saveProfile}>
              <fieldset disabled={saving} className="form-fieldset">
                <div className="form-grid">
                  <Label className="items-stretch">
                    Nome
                    <Input
                      required
                      maxLength="120"
                      value={profile.name || ''}
                      onChange={input(setProfile, 'name', markProfile)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Data de nascimento
                    <Input
                      type="date"
                      value={profile.birth_date || ''}
                      onChange={input(setProfile, 'birth_date', markProfile)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Altura (cm)
                    <Input
                      type="number"
                      min="50"
                      max="260"
                      step="0.1"
                      value={profile.height_cm ?? ''}
                      onChange={input(setProfile, 'height_cm', markProfile)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Peso de referência (kg)
                    <Input
                      type="number"
                      min="20"
                      max="500"
                      step="0.1"
                      value={profile.weight_kg ?? ''}
                      onChange={input(setProfile, 'weight_kg', markProfile)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Sexo usado na fórmula de gasto
                    <NativeSelect
                      className="w-full min-w-0"
                      value={profile.sex || ''}
                      onChange={input(setProfile, 'sex', markProfile)}
                    >
                      <option value="">Não informado</option>
                      <option value="male">Masculino</option>
                      <option value="female">Feminino</option>
                    </NativeSelect>
                  </Label>
                  <Label className="items-stretch">
                    Gasto diário de referência, se informado (kcal)
                    <Input
                      type="number"
                      min="500"
                      max="10000"
                      value={profile.manual_tdee_kcal ?? ''}
                      onChange={input(setProfile, 'manual_tdee_kcal', markProfile)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Fuso horário
                    <Input
                      value={profile.timezone || 'America/Sao_Paulo'}
                      onChange={input(setProfile, 'timezone', markProfile)}
                    />
                  </Label>
                </div>
              </fieldset>
              <Button variant="default" className="primary" disabled={saving || model.loading}>
                Salvar perfil
              </Button>
            </form>
          </Section>
          <details className="panel">
            <summary className="section-summary">Preferências e acompanhamento</summary>
            <form
              className="personal-form"
              onSubmit={(event) => {
                event.preventDefault();
                commit(
                  'preferences',
                  {
                    ...preferences,
                    ...Object.fromEntries(
                      [
                        'activity_factor',
                        'review_days',
                        'review_frequency_days',
                        'min_complete_days',
                        'min_weight_measurements',
                        'adjustment_kcal',
                      ].map((key) => [key, optionalNumber(preferences[key])]),
                    ),
                  },
                  'Preferências atualizadas.',
                );
              }}
            >
              <fieldset disabled={saving} className="form-fieldset">
                <div className="form-grid">
                  <Label className="items-stretch">
                    Referência preferida para o gasto
                    <NativeSelect
                      className="w-full min-w-0"
                      value={preferences.energy_method || 'auto'}
                      onChange={input(setPreferences, 'energy_method', markPreferences)}
                    >
                      <option value="auto">Automático · total completo ou modelo</option>
                      <option value="model">Modelo a partir do perfil</option>
                      <option value="wearable">Somente relógio ou plataforma</option>
                    </NativeSelect>
                  </Label>
                  <Label className="items-stretch">
                    Fator de atividade para gasto modelado
                    <NativeSelect
                      className="w-full min-w-0"
                      value={preferences.activity_factor ?? ''}
                      onChange={input(setPreferences, 'activity_factor', markPreferences)}
                    >
                      <option value="">Não informado</option>
                      <option value="1.2">1,20 · rotina sedentária</option>
                      <option value="1.375">1,375 · atividade leve</option>
                      <option value="1.55">1,55 · atividade moderada</option>
                      <option value="1.725">1,725 · atividade intensa</option>
                      <option value="1.9">1,90 · atividade muito intensa</option>
                    </NativeSelect>
                  </Label>
                  {[
                    ['review_frequency_days', 'Intervalo entre revisões (dias)', 1, 90, 7],
                    ['review_days', 'Janela de evidência (dias)', 7, 90, 14],
                    ['min_complete_days', 'Dias completos exigidos', 1, 90, 10],
                    ['min_weight_measurements', 'Medidas de peso exigidas', 4, 90, 4],
                    ['adjustment_kcal', 'Passo de ajuste energético (kcal)', 25, 200, 100],
                  ].map(([key, label, min, max, fallback]) => (
                    <Label className="items-stretch" key={key}>
                      {label}
                      <Input
                        type="number"
                        min={min}
                        max={max}
                        value={preferences[key] ?? fallback}
                        onChange={input(setPreferences, key, markPreferences)}
                      />
                    </Label>
                  ))}
                  {[
                    ['modalities', 'Modalidades e rotina'],
                    ['food_preferences', 'Preferências alimentares'],
                    ['allergies', 'Alergias declaradas'],
                    ['restrictions', 'Restrições e orientações registradas'],
                  ].map(([key, label]) => (
                    <div className="wide flex flex-col gap-2" key={key}>
                      <Label htmlFor={`${fieldId}-preferences-${key}`}>{label}</Label>
                      <Textarea
                        id={`${fieldId}-preferences-${key}`}
                        rows="2"
                        maxLength="5000"
                        value={
                          Array.isArray(preferences[key])
                            ? preferences[key].join(', ')
                            : preferences[key] || ''
                        }
                        onChange={input(setPreferences, key, markPreferences)}
                      />
                    </div>
                  ))}
                </div>
                <p className="small muted">
                  As fontes são alternativas e não são somadas. O fator de atividade já inclui a
                  atividade habitual.
                </p>
                <Label htmlFor="profile-review-reminders" className="checkbox-label">
                  <Checkbox
                    id="profile-review-reminders"
                    checked={preferences.review_reminders !== false}
                    onCheckedChange={(checked) => {
                      markPreferences();
                      setPreferences((value) => ({ ...value, review_reminders: checked === true }));
                    }}
                  />
                  Lembrar as revisões do plano
                </Label>
              </fieldset>
              <Button variant="default" className="primary" disabled={saving || model.loading}>
                Salvar preferências
              </Button>
            </form>
          </details>
          <Section
            title={measure.id ? 'Editar medida corporal' : 'Nova medida corporal'}
            description="Registre a data e o método da medição."
          >
            <form className="personal-form" onSubmit={saveMeasure}>
              <fieldset disabled={saving} className="form-fieldset">
                <div className="form-grid">
                  <Label className="items-stretch">
                    Data
                    <Input
                      type="date"
                      required
                      value={measure.date}
                      onChange={input(setMeasure, 'date', markMeasure)}
                    />
                  </Label>
                  <Label className="items-stretch">
                    Método
                    <Input
                      maxLength="200"
                      value={measure.method}
                      onChange={input(setMeasure, 'method', markMeasure)}
                      placeholder="Balança, bioimpedância, antropometria…"
                    />
                  </Label>
                  {[
                    ['weight_kg', 'Peso (kg)', 500],
                    ['waist_cm', 'Cintura (cm)', 300],
                    ['body_fat_pct', 'Gordura corporal (%)', 100],
                    ['lean_mass_kg', 'Massa magra (kg)', 500],
                  ].map(([key, label, max]) => (
                    <Label className="items-stretch" key={key}>
                      {label}
                      <Input
                        type="number"
                        min="0"
                        max={max}
                        step="0.1"
                        value={measure[key]}
                        onChange={input(setMeasure, key, markMeasure)}
                      />
                    </Label>
                  ))}
                  <div className="wide flex flex-col gap-2">
                    <Label htmlFor={`${fieldId}-measure-notes`}>Notas</Label>
                    <Textarea
                      id={`${fieldId}-measure-notes`}
                      rows="2"
                      value={measure.notes || ''}
                      onChange={input(setMeasure, 'notes', markMeasure)}
                    />
                  </div>
                </div>
              </fieldset>
              <div className="report-actions">
                <Button variant="default" className="primary" disabled={saving || model.loading}>
                  Salvar medida
                </Button>
                {measure.id && (
                  <Button
                    variant="outline"
                    type="button"
                    disabled={saving}
                    onClick={() => {
                      if (
                        !measureDirty ||
                        window.confirm('Descartar as alterações desta medida?')
                      ) {
                        setMeasure(blankMeasure(day));
                        setMeasureDirty(false);
                      }
                    }}
                  >
                    Cancelar edição
                  </Button>
                )}
              </div>
            </form>
            <PagedList items={measures} label="Medidas corporais">
              {(rows) => (
                <div className="record-list">
                  {rows.map((row) => (
                    <div className="record-row" key={row.id}>
                      <div>
                        <strong>{dayLabel(row.date)}</strong>
                        <p>
                          {[
                            ['weight_kg', 'kg'],
                            ['waist_cm', 'cm cintura'],
                            ['body_fat_pct', '% gordura'],
                            ['lean_mass_kg', 'kg massa magra'],
                          ]
                            .filter(([key]) => row[key] != null)
                            .map(([key, unit]) => `${format(row[key])} ${unit}`)
                            .join(' · ') || 'Sem valores'}
                          <span className="small muted block">
                            {row.method || 'Método não informado'}
                            {row.notes ? ' · ' + row.notes : ''}
                          </span>
                        </p>
                      </div>
                      <div className="report-actions">
                        <Button
                          variant="outline"
                          type="button"
                          disabled={saving}
                          onClick={() => editMeasure(row)}
                        >
                          Editar
                        </Button>
                        <Button
                          variant="outline"
                          type="button"
                          disabled={saving || model.loading}
                          onClick={async () => {
                            if (!window.confirm('Remover esta medida corporal?')) return;
                            await commit('measurements', row, 'Medida removida.', true);
                          }}
                        >
                          Remover
                        </Button>
                      </div>
                    </div>
                  ))}
                  {!measures.length && <p className="empty">Nenhuma medida pessoal registrada.</p>}
                </div>
              )}
            </PagedList>
          </Section>
          <Section title="Contexto do dia">
            <div className="filters">
              <Label className="items-stretch">
                Dia
                <Input
                  type="date"
                  disabled={saving || dirty}
                  value={day}
                  onChange={(e) => {
                    setEnergyState({ busy: false, dirty: false });
                    setDay(e.target.value);
                  }}
                />
              </Label>
              <Button
                variant="outline"
                disabled={saving}
                onClick={() => {
                  setCheckinState({ busy: false, dirty: false });
                  setCheckinOpen(true);
                }}
              >
                Registrar ou editar check-in
              </Button>
            </div>
          </Section>
          <EnergyEditor key={day} day={day} model={model} onStateChange={setEnergyState} />
          {Chart && (
            <Section title="Evolução das medidas pessoais">
              <div className="split">
                <div>
                  <h3>Peso registrado</h3>
                  <Chart
                    rows={measures.slice().reverse()}
                    keys={[{ key: 'weight_kg', label: 'Peso (kg)', color: '#3fb950' }]}
                    points
                    height={230}
                  />
                </div>
                <div>
                  <h3>Cintura registrada</h3>
                  <Chart
                    rows={measures.slice().reverse()}
                    keys={[{ key: 'waist_cm', label: 'Cintura (cm)', color: '#f78166' }]}
                    points
                    height={230}
                  />
                </div>
              </div>
            </Section>
          )}
        </>
      )}
      {checkinOpen && (
        <Modal
          title={`Check-in · ${dayLabel(day)}`}
          onClose={() => {
            setCheckinOpen(false);
            setCheckinState({ busy: false, dirty: false });
          }}
          busy={checkinState.busy}
          dirty={checkinState.dirty}
        >
          <CheckinForm
            day={day}
            model={model}
            onStateChange={setCheckinState}
            onSaved={() => {
              setCheckinOpen(false);
              setCheckinState({ busy: false, dirty: false });
            }}
          />
        </Modal>
      )}
    </>
  );
}
