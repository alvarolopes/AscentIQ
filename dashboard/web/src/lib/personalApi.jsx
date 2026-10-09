'use client';

import React, { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '@/lib/api/client';
import { calendarDay, displayDay } from '@/lib/dates';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

export const today = calendarDay;
export const dayLabel = displayDay;
export const format = (value, digits = 1) =>
  value == null || value === ''
    ? 'Sem dado'
    : Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });
export const optionalNumber = (value) => (value === '' || value == null ? null : Number(value));
export const array = (value) => (Array.isArray(value) ? value : []);
export const personalApi = apiRequest;

export function notifyIntegrationChange() {
  window.dispatchEvent(new Event('ascentiq-integrations-changed'));
  try {
    localStorage.setItem('ascentiq-integrations-updated', String(Date.now()));
  } catch {}
}

export function usePersonal(day, days = 14) {
  const query = useQuery({
    queryKey: ['personal', day, days],
    queryFn: ({ signal }) =>
      personalApi(`personal?day=${encodeURIComponent(day)}&days=${days}`, undefined, signal),
  });
  const refetch = query.refetch;
  const load = useCallback(async () => {
    const result = await refetch();
    if (result.error) throw result.error;
    return result.data;
  }, [refetch]);
  const value = query.data || null;
  async function save(kind, record, remove = false) {
    try {
      const revision = value?.state?.revision;
      const body = remove
        ? { id: record.id, revision }
        : ['profile', 'preferences'].includes(kind)
          ? { value: record, revision }
          : { record, revision };
      await personalApi(`personal/${kind}${remove ? '/remove' : ''}`, body);
      return await load();
    } catch (error) {
      if (error.status === 409) await load().catch(() => {});
      throw error;
    }
  }
  return {
    value,
    state: value?.state || {},
    summary: value?.summary || {},
    loading: query.isPending,
    error: query.error?.message || '',
    load,
    save,
  };
}

export function ErrorNotice({ error }) {
  return error ? (
    <Alert variant="destructive" role="alert" className="mb-4">
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  ) : null;
}
export function StatusNotice({ message }) {
  return message ? (
    <Alert role="status" className="mb-4">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  ) : null;
}
export function PageHeading({ kicker, title, children }) {
  return (
    <header className="mb-5 flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{kicker}</p>
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children ? <p className="text-sm text-muted-foreground">{children}</p> : null}
    </header>
  );
}
export function PersonalLoading({ model }) {
  return (
    <>
      <ErrorNotice error={model.error} />
      {model.loading ? (
        <div role="status" className="mb-4 flex flex-col gap-2">
          <span className="text-sm text-muted-foreground">Consultando seus registros…</span>
          <Skeleton className="h-4 w-40" />
        </div>
      ) : null}
      {model.error ? (
        <Button variant="outline" onClick={() => model.load().catch(() => {})}>
          Tentar novamente
        </Button>
      ) : null}
    </>
  );
}
