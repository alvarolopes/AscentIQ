'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
  type RefObject,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { apiRequest, ApiError } from '@/lib/api/client';
import { snapshotSchema, jobsSchema, sessionSchema, type Snapshot } from '@/lib/api/contracts';

export type ModalName = 'goals' | 'profile' | 'settings' | 'documents' | 'training-analysis';
type State = { busy: boolean; dirty: boolean };
type Platform = {
  data: Snapshot | null;
  error: string;
  busy: boolean;
  activeJob: string | null;
  selectedDay: string;
  refresh: () => Promise<unknown>;
  onJob: (mode: string) => Promise<void>;
  navigate: (target: string, day?: string) => void;
  openAssistant: (day?: string) => void;
  modal: ModalName | null;
  modalFocusRef: RefObject<HTMLElement | null>;
  modalState: State;
  setModalState: (state: State) => void;
  closeModal: () => void;
  assistantStarted: boolean;
  assistantOpen: boolean;
  assistantMinimized: boolean;
  setAssistantOpen: (open: boolean) => void;
  setAssistantMinimized: (minimized: boolean) => void;
  logout: () => Promise<void>;
};
const Context = createContext<Platform | null>(null);
const routes: Record<string, string> = {
  dashboard: '/',
  today: '/',
  workouts: '/workouts',
  overview: '/workouts',
  running: '/workouts/running',
  strength: '/workouts/strength',
  nutrition: '/nutrition',
  sleep: '/sleep',
};
const modalNames = ['goals', 'profile', 'settings', 'documents', 'training-analysis'];

export function PlatformProvider({
  children,
  initialDay,
}: {
  children: ReactNode;
  initialDay: string;
}) {
  const modalFocusRef = useRef<HTMLElement | null>(null);
  const router = useRouter(),
    client = useQueryClient();
  const [selectedDay, setSelectedDay] = useState(initialDay),
    [modal, setModal] = useState<ModalName | null>(null);
  const [modalState, setModalState] = useState<State>({ busy: false, dirty: false }),
    [operationError, setOperationError] = useState('');
  const [assistantStarted, setAssistantStarted] = useState(false),
    [assistantOpen, setAssistantOpen] = useState(false),
    [assistantMinimized, setAssistantMinimized] = useState(false);
  const dashboard = useQuery({
    queryKey: ['dashboard'],
    queryFn: async ({ signal }) =>
      snapshotSchema.parse(await apiRequest('dashboard', undefined, signal)),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  });
  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: async ({ signal }) => jobsSchema.parse(await apiRequest('jobs', undefined, signal)),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  });
  const refresh = useCallback(
    () =>
      client.invalidateQueries({
        predicate: (query) =>
          [
            'dashboard',
            'jobs',
            'personal',
            'food',
            'nutrition-targets',
            'frequency',
            'daily-analysis',
          ].includes(String(query.queryKey[0])),
      }),
    [client],
  );
  const expire = useCallback(() => {
    void client.cancelQueries();
    client.clear();
    setModal(null);
    setAssistantStarted(false);
    window.location.replace('/login');
  }, [client]);
  useEffect(() => {
    const revalidate = () => {
      void apiRequest('auth/session')
        .then((value) => sessionSchema.parse(value))
        .catch((error) => {
          if (error instanceof ApiError && error.status === 401) expire();
        });
    };
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) revalidate();
    };
    const integrations = () => {
      void refresh();
    };
    window.addEventListener('ascentiq-session-expired', expire);
    window.addEventListener('focus', revalidate);
    window.addEventListener('pageshow', onShow);
    window.addEventListener('ascentiq-integrations-changed', integrations);
    return () => {
      window.removeEventListener('ascentiq-session-expired', expire);
      window.removeEventListener('focus', revalidate);
      window.removeEventListener('pageshow', onShow);
      window.removeEventListener('ascentiq-integrations-changed', integrations);
    };
  }, [expire, refresh]);
  function openAssistant(day?: string) {
    if (day) setSelectedDay(day);
    setAssistantStarted(true);
    setAssistantOpen(true);
    setAssistantMinimized(false);
  }
  function navigate(target: string, day?: string) {
    if (
      modal &&
      (modalState.busy ||
        (modalState.dirty && !window.confirm('Descartar as alterações ainda não salvas?')))
    )
      return;
    if (day) setSelectedDay(day);
    if (target === 'assistant') {
      openAssistant(day);
      return;
    }
    if (modalNames.includes(target)) {
      if (!modal) {
        const active =
          document.activeElement instanceof HTMLElement ? document.activeElement : null;
        modalFocusRef.current =
          active?.getAttribute('role') === 'menuitem'
            ? document.querySelector<HTMLElement>('[data-account-trigger]')
            : active;
      }
      setModalState({ busy: false, dirty: false });
      setModal(target as ModalName);
      return;
    }
    setModal(null);
    router.push(routes[target] ?? '/');
  }
  async function onJob(mode: string) {
    try {
      setOperationError('');
      await apiRequest('jobs', { mode });
      await refresh();
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : 'Não foi possível atualizar.');
    }
  }
  async function logout() {
    if (modalState.busy) return;
    if (modalState.dirty && !window.confirm('Descartar as alterações ainda não salvas e sair?'))
      return;
    try {
      await apiRequest('auth/logout', {});
      expire();
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : 'Não foi possível sair.');
    }
  }
  const active = jobs.data?.jobs.find((job) => ['queued', 'running'].includes(job.status));
  return (
    <Context.Provider
      value={{
        data: dashboard.data ?? null,
        error: operationError || dashboard.error?.message || jobs.error?.message || '',
        busy: Boolean(active),
        activeJob: active?.message ?? null,
        selectedDay,
        refresh,
        onJob,
        navigate,
        openAssistant,
        modal,
        modalFocusRef,
        modalState,
        setModalState,
        closeModal: () => {
          setModal(null);
          setModalState({ busy: false, dirty: false });
          void refresh();
        },
        assistantStarted,
        assistantOpen,
        assistantMinimized,
        setAssistantOpen,
        setAssistantMinimized,
        logout,
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function usePlatform() {
  const value = useContext(Context);
  if (!value) throw new Error('PlatformProvider ausente.');
  return value;
}
