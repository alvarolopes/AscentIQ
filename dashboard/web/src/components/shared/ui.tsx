'use client';

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Info, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { cn } from '@/lib/utils';

type ModalProps = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
  dirty?: boolean;
  className?: string;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

export function Modal({
  title,
  onClose,
  children,
  busy = false,
  dirty = false,
  className = '',
  returnFocusRef,
}: ModalProps) {
  const [discard, setDiscard] = useState(false);
  const origin = useRef<HTMLElement | null>(null);
  const draftFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!dirty && !busy) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [dirty, busy]);
  function close() {
    if (busy) return;
    if (dirty) {
      draftFocus.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setDiscard(true);
      return;
    }
    onClose();
  }
  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent
          showCloseButton={false}
          className={cn(
            'max-h-[90dvh] overflow-y-auto overscroll-contain sm:max-w-3xl',
            className === 'modal-wide' && 'sm:max-w-6xl',
            className,
          )}
          aria-busy={busy}
          onOpenAutoFocus={() => {
            origin.current =
              returnFocusRef?.current ??
              (document.activeElement instanceof HTMLElement ? document.activeElement : null);
          }}
          onEscapeKeyDown={(event) => {
            event.preventDefault();
            if (!discard) close();
          }}
          onPointerDownOutside={(event) => {
            event.preventDefault();
            if (!discard) close();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = returnFocusRef?.current ?? origin.current;
            requestAnimationFrame(() => {
              if (target?.isConnected) target.focus();
            });
          }}
        >
          <DialogHeader className="flex-row items-center justify-between gap-4">
            <div>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription className="sr-only">
                Consulte ou atualize seus registros. Alterações não salvas são protegidas.
              </DialogDescription>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Fechar ${title}`}
              disabled={busy}
              onClick={close}
            >
              <X />
            </Button>
          </DialogHeader>
          <div className="modal-body">{children}</div>
        </DialogContent>
      </Dialog>
      <AlertDialog open={discard} onOpenChange={setDiscard}>
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = draftFocus.current;
            requestAnimationFrame(() => {
              if (target?.isConnected) target.focus();
            });
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>Descartar rascunho?</AlertDialogTitle>
            <AlertDialogDescription>As alterações ainda não foram salvas.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Continuar editando</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDiscard(false);
                onClose();
              }}
            >
              Descartar rascunho
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export function InfoButton({
  title = 'Como interpretar',
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={title}
        title={title}
        onClick={() => setOpen(true)}
      >
        <Info />
      </Button>
      {open ? (
        <Modal title={title} onClose={() => setOpen(false)}>
          {children}
        </Modal>
      ) : null}
    </>
  );
}

type Pagination = { page?: number; page_size?: number; pages?: number; total?: number };
type PagedProps<T> = {
  items?: T[];
  children?: ReactNode | ((items: T[]) => ReactNode);
  renderItem?: (item: T, index: number) => ReactNode;
  resetKey?: string;
  label?: string;
  empty?: ReactNode;
  pagination?: Pagination;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
};

export function PagedList<T>({
  items = [],
  children,
  renderItem,
  resetKey = '',
  label = 'registros',
  empty = null,
  pagination,
  onPageChange,
  onPageSizeChange,
}: PagedProps<T>) {
  const [selection, setSelection] = useState({ key: resetKey, page: 1, size: 10 });
  const state =
    selection.key === resetKey ? selection : { key: resetKey, page: 1, size: selection.size };
  const size = pagination ? (pagination.page_size === 15 ? 15 : 10) : state.size;
  const total = pagination?.total ?? items.length;
  const pages = Math.max(1, pagination?.pages ?? Math.ceil(total / size));
  const page = Math.min(pagination?.page ?? state.page, pages);
  const visible = pagination ? items.slice(0, size) : items.slice((page - 1) * size, page * size);
  const setPage = (value: number) =>
    pagination ? onPageChange?.(value) : setSelection({ ...state, page: value });
  return (
    <div className="paged-list">
      {total || !empty
        ? typeof children === 'function'
          ? children(visible)
          : renderItem
            ? visible.map(renderItem)
            : children
        : empty}
      {total > 10 ? (
        <nav className="pagination" aria-label={`Paginação de ${label}`}>
          <span className="text-xs text-muted-foreground">
            {(page - 1) * size + 1}–{Math.min((page - 1) * size + visible.length, total)} de {total}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs">
              Por página
              <NativeSelect
                aria-label={`Registros por página de ${label}`}
                value={size}
                onChange={(event) => {
                  const value = Number(event.target.value) === 15 ? 15 : 10;
                  if (pagination) onPageSizeChange?.(value);
                  else setSelection({ ...state, size: value, page: 1 });
                }}
              >
                <NativeSelectOption value={10}>10</NativeSelectOption>
                <NativeSelectOption value={15}>15</NativeSelectOption>
              </NativeSelect>
            </label>
            <Button
              type="button"
              variant="outline"
              disabled={page <= 1}
              aria-label={`Página anterior de ${label}`}
              onClick={() => setPage(page - 1)}
            >
              Anterior
            </Button>
            <span className="text-xs" aria-live="polite">
              {page} / {pages}
            </span>
            <Button
              type="button"
              variant="outline"
              disabled={page >= pages}
              aria-label={`Próxima página de ${label}`}
              onClick={() => setPage(page + 1)}
            >
              Próxima
            </Button>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
