'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  ChevronDown,
  Dumbbell,
  LayoutDashboard,
  Menu,
  MessageCircle,
  Minimize2,
  Moon,
  Utensils,
  X,
} from 'lucide-react';
import { usePlatform, type ModalName } from '@/providers/platform-provider';
import { Logo } from './logo';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Modal } from '@/components/shared/ui';
import { Chart } from '@/components/shared/charts';
import { displayDay } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';

const Goals = dynamic(() => import('@/features/goals/Goals'));
const Profile = dynamic(() => import('@/features/profile/Health'));
const Settings = dynamic(() => import('@/features/settings/Settings'));
const Documents = dynamic(() => import('@/features/documents/Documents'));
const DailyAnalysis = dynamic(() => import('@/features/analyses/DailyAnalysis'));
const Assistant = dynamic(() => import('@/features/assistant/Assistant'));
const InstallApp = dynamic(() => import('@/features/pwa/InstallApp'));
const navigation = [
  { id: 'dashboard', name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { id: 'workouts', name: 'Workouts', path: '/workouts', icon: Dumbbell },
  { id: 'nutrition', name: 'Nutrition', path: '/nutrition', icon: Utensils },
  { id: 'sleep', name: 'Sleep', path: '/sleep', icon: Moon },
];
const titles: Record<ModalName, string> = {
  goals: 'Objetivos e plano',
  profile: 'Perfil e medidas',
  settings: 'Dados e fontes',
  documents: 'Documentos privados',
  'training-analysis': 'Análise dos treinos',
};

export default function PlatformShell({
  children,
  username,
}: {
  children: React.ReactNode;
  username: string;
}) {
  const state = usePlatform(),
    path = usePathname(),
    [mobile, setMobile] = useState(false);
  useEffect(() => {
    const wide = window.matchMedia('(min-width: 1024px)');
    const changed = () => {
      if (wide.matches) setMobile(false);
    };
    wide.addEventListener('change', changed);
    return () => wide.removeEventListener('change', changed);
  }, []);
  const workouts = path.startsWith('/workouts'),
    name = state.data?.athlete.name ?? username;
  function navigate(id: string) {
    state.navigate(id);
    setMobile(false);
  }
  const links = (
    <nav aria-label="Áreas do painel" className="flex flex-col gap-1">
      {navigation.map((item) => {
        const selected = item.path === '/' ? path === '/' : path.startsWith(item.path);
        const Icon = item.icon;
        return (
          <Button
            asChild
            key={item.id}
            variant={selected ? 'secondary' : 'ghost'}
            className="justify-start gap-3 text-primary hover:text-primary"
          >
            <Link
              href={item.path}
              prefetch={false}
              aria-current={selected ? 'page' : undefined}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                navigate(item.id);
              }}
            >
              <Icon data-icon="inline-start" />
              {item.name}
            </Link>
          </Button>
        );
      })}
    </nav>
  );
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-background focus:p-3"
      >
        Ir para o conteúdo
      </a>
      <header
        className="fixed inset-x-0 top-0 z-40 flex min-h-18 items-center justify-between gap-3 border-b bg-card px-4 py-3 sm:px-6"
        data-testid="topbar"
      >
        <div className="flex items-center gap-3">
          <Popover open={mobile} onOpenChange={setMobile} modal>
            <PopoverTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                aria-label="Abrir menu principal"
                aria-expanded={mobile}
              >
                <Menu />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              align="start"
              sideOffset={16}
              className="w-60 rounded-2xl p-4 lg:hidden"
              aria-label="Menu principal mobile"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">SEU PAINEL</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Fechar menu principal"
                  onClick={() => setMobile(false)}
                >
                  <X />
                </Button>
              </div>
              {links}
            </PopoverContent>
          </Popover>
          <Logo />
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-muted-foreground sm:inline-flex sm:items-center sm:gap-2">
            <Activity className="size-3" />
            {state.busy
              ? 'Atualização em andamento'
              : `Treinos: ${displayDay(state.data?.freshness.activities)}`}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" data-account-trigger aria-label={`Menu da conta de ${name}`}>
                <Avatar className="size-8">
                  <AvatarFallback>{name.slice(0, 2).toUpperCase()}</AvatarFallback>
                </Avatar>
                <span className="hidden max-w-36 truncate sm:block">{name}</span>
                <ChevronDown data-icon="inline-end" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuLabel>{name}</DropdownMenuLabel>
              <DropdownMenuGroup>
                <DropdownMenuItem onSelect={() => state.navigate('profile')}>
                  Conta e perfil
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => state.navigate('settings')}>
                  Dados e fontes
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuItem onSelect={() => void state.logout()}>Sair</DropdownMenuItem>
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <div
        className="mx-auto mt-24 grid w-[calc(100%-2rem)] max-w-[1440px] items-start gap-6 pb-6 sm:w-[calc(100%-3rem)] lg:grid-cols-[220px_minmax(0,1fr)]"
        data-testid="boxed-layout"
      >
        <aside
          className="sticky top-25 hidden rounded-2xl border bg-card p-4 lg:block"
          data-testid="sidebar"
        >
          <p className="mb-3 text-[10px] tracking-widest text-muted-foreground">SEU PAINEL</p>
          {links}
        </aside>
        <main id="main-content" className="min-w-0" tabIndex={-1}>
          {workouts ? (
            <nav
              aria-label="Áreas de Workouts"
              className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border bg-card p-2"
            >
              {[
                ['overview', 'Visão geral', '/workouts'],
                ['running', 'Corrida', '/workouts/running'],
                ['strength', 'Força', '/workouts/strength'],
              ].map(([id, label, url]) => (
                <Button asChild key={id} variant={path === url ? 'secondary' : 'ghost'}>
                  <Link
                    href={url}
                    prefetch={false}
                    aria-current={path === url ? 'page' : undefined}
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                      event.preventDefault();
                      state.navigate(id);
                    }}
                  >
                    {label}
                  </Link>
                </Button>
              ))}
              {path === '/workouts' ? (
                <Button className="ml-auto" onClick={() => state.navigate('training-analysis')}>
                  Analisar treinos do dia
                </Button>
              ) : null}
            </nav>
          ) : null}
          {state.error ? (
            <Alert variant="destructive" role="alert" className="mb-5">
              <AlertDescription className="flex flex-wrap items-center gap-3">
                {state.error}
                <Button variant="outline" onClick={() => void state.refresh()}>
                  Tentar novamente
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
          {state.activeJob ? (
            <Alert role="status" className="mb-5">
              <AlertDescription>
                {state.activeJob}. Você pode continuar consultando a última versão.
              </AlertDescription>
            </Alert>
          ) : null}
          {state.data?.sync_warnings?.length ? (
            <Alert className="mb-5">
              <AlertDescription>
                Atualização parcial: {state.data.sync_warnings.join(' ')}
              </AlertDescription>
            </Alert>
          ) : null}
          {!state.data ? (
            <Card>
              <CardContent className="flex flex-col gap-4 pt-6" role="status">
                <span>Preparando seu histórico…</span>
                <Skeleton className="h-8 w-2/3" />
                <Skeleton className="h-32 w-full" />
              </CardContent>
            </Card>
          ) : (
            children
          )}
          <footer className="mt-6 flex flex-wrap justify-between gap-2 border-t pt-4 text-[10px] text-muted-foreground">
            <span>ASCENTIQ · Seus registros. Dados de saúde privados.</span>
            <span>
              {state.data?.storage?.backend === 'postgres' ? 'PostgreSQL local · ' : ''}
              {state.data?.generated_at
                ? `Snapshot: ${new Date(state.data.generated_at).toLocaleString('pt-BR')}`
                : ''}
            </span>
          </footer>
        </main>
      </div>
      {state.modal ? (
        <Modal
          title={titles[state.modal]}
          className="modal-wide"
          busy={state.modalState.busy}
          dirty={state.modalState.dirty}
          returnFocusRef={state.modalFocusRef}
          onClose={state.closeModal}
        >
          {state.modal === 'goals' ? (
            <Goals initialDay={state.selectedDay} onStateChange={state.setModalState} />
          ) : null}
          {state.modal === 'profile' ? (
            <Profile
              Chart={Chart}
              initialDay={state.selectedDay}
              onStateChange={state.setModalState}
            />
          ) : null}
          {state.modal === 'settings' ? (
            <>
              <div className="mb-4">
                <Button variant="outline" onClick={() => state.navigate('documents')}>
                  Documentos privados
                </Button>
              </div>
              <Settings
                onJob={state.onJob}
                busy={state.busy}
                initialDay={state.selectedDay}
                onStateChange={state.setModalState}
              />
            </>
          ) : null}
          {state.modal === 'documents' ? (
            <Documents initialDay={state.selectedDay} onStateChange={state.setModalState} />
          ) : null}
          {state.modal === 'training-analysis' && state.data ? (
            <DailyAnalysis data={state.data} onStateChange={state.setModalState} />
          ) : null}
        </Modal>
      ) : null}
      {state.assistantStarted ? (
        <section
          aria-label="Assistente pessoal"
          hidden={!state.assistantOpen || state.assistantMinimized}
          className={cn(
            'fixed bottom-4 left-4 z-30 flex max-h-[78dvh] w-[calc(100%-2rem)] max-w-md flex-col rounded-2xl border bg-card shadow-xl xl:left-[max(1.5rem,calc((100vw-1440px)/2))]',
            (!state.assistantOpen || state.assistantMinimized) && 'hidden',
          )}
        >
          <header className="flex items-center justify-between gap-2 border-b p-3">
            <div>
              <strong className="text-sm">Seu assistente</strong>
              <p className="text-xs text-muted-foreground">Converse com seus registros</p>
            </div>
            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Minimizar assistente"
                onClick={() => state.setAssistantMinimized(true)}
              >
                <Minimize2 />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Fechar assistente"
                onClick={() => state.setAssistantOpen(false)}
              >
                <X />
              </Button>
            </div>
          </header>
          <div className="min-h-0 overflow-y-auto p-4">
            <Assistant compact day={state.selectedDay} />
          </div>
        </section>
      ) : null}
      {state.assistantOpen && state.assistantMinimized ? (
        <Button
          className="fixed bottom-4 left-4 z-30"
          onClick={() => state.setAssistantMinimized(false)}
        >
          <MessageCircle data-icon="inline-start" />
          Abrir assistente
        </Button>
      ) : null}
      <InstallApp />
    </>
  );
}
