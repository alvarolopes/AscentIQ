'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { array, ErrorNotice, optionalNumber, StatusNotice } from '@/lib/personalApi';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
const scores = [
  ['fatigue', 'Fadiga · 0 nenhuma, 10 extrema'],
  ['hunger', 'Fome · 0 nenhuma, 10 extrema'],
  ['mood', 'Disposição · 0 baixa, 10 ótima'],
  ['pain', 'Dor · 0 nenhuma, 10 extrema'],
  ['stress', 'Estresse · 0 nenhum, 10 extremo'],
];
const blankCheckin = (day) => ({
  date: day,
  fatigue: '',
  hunger: '',
  mood: '',
  pain: '',
  stress: '',
  sleep_hours: '',
  illness: false,
  notes: '',
});
export default function CheckinForm({ day, model, onSaved, onStateChange, onDirtyChange }) {
  const existing = array(model.state.checkins).find((row) => row.date === day),
    id = useId();
  const [draft, setDraft] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [saved, setSaved] = useState('');
  const dirty = draft?.day === day,
    form = dirty ? draft.value : existing ? { ...existing } : blankCheckin(day),
    lock = useRef(false);
  useEffect(() => {
    onStateChange?.({ busy, dirty });
    onDirtyChange?.(dirty);
  }, [busy, dirty, onStateChange, onDirtyChange]);
  const field = (key, value) => setDraft({ day, value: { ...form, [key]: value } });
  async function submit(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      await model.save('checkins', {
        ...form,
        date: day,
        ...Object.fromEntries(
          [...scores.map(([key]) => key), 'sleep_hours'].map((key) => [
            key,
            optionalNumber(form[key]),
          ]),
        ),
      });
      setDraft(null);
      setSaved('Check-in salvo.');
      onSaved?.();
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function remove() {
    if (lock.current || !window.confirm('Remover o check-in deste dia?')) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      await model.save('checkins', existing, true);
      setDraft(null);
      setSaved('Check-in removido.');
      onSaved?.();
    } catch (e) {
      setError(e.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <form className="personal-form" onSubmit={submit}>
      <ErrorNotice error={error} />
      <StatusNotice message={saved} />
      <fieldset disabled={busy} className="form-fieldset">
        <FieldGroup className="form-grid">
          {scores.map(([key, label]) => (
            <Field key={key}>
              <FieldLabel htmlFor={id + '-' + key}>{label}</FieldLabel>
              <Input
                id={id + '-' + key}
                type="number"
                min="0"
                max="10"
                step="1"
                value={form[key] ?? ''}
                onChange={(e) => field(key, e.target.value)}
              />
            </Field>
          ))}
          <Field>
            <FieldLabel htmlFor={id + '-sleep'}>Sono informado (horas)</FieldLabel>
            <Input
              id={id + '-sleep'}
              type="number"
              min="0"
              max="24"
              step="0.1"
              value={form.sleep_hours ?? ''}
              onChange={(e) => field('sleep_hours', e.target.value)}
            />
          </Field>
          <Field orientation="horizontal">
            <Checkbox
              id={id + '-illness'}
              checked={Boolean(form.illness)}
              onCheckedChange={(value) => field('illness', value === true)}
            />
            <FieldLabel htmlFor={id + '-illness'}>Estou com sinais de doença</FieldLabel>
          </Field>
          <Field className="wide">
            <FieldLabel htmlFor={id + '-notes'}>Como você está hoje?</FieldLabel>
            <Textarea
              id={id + '-notes'}
              rows={3}
              maxLength={5000}
              value={form.notes || ''}
              onChange={(e) => field('notes', e.target.value)}
              placeholder="Contexto que ajude a interpretar o dia"
            />
          </Field>
        </FieldGroup>
      </fieldset>
      <div className="report-actions">
        <Button disabled={busy || model.loading}>
          {busy ? 'Salvando…' : existing ? 'Atualizar check-in' : 'Salvar check-in'}
        </Button>
        {existing && (
          <Button type="button" variant="outline" disabled={busy || model.loading} onClick={remove}>
            Remover check-in
          </Button>
        )}
      </div>
      <p className="small muted">Campos opcionais. Um campo vazio continua desconhecido.</p>
    </form>
  );
}
