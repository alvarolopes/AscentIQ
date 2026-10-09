import { Skeleton } from '@/components/ui/skeleton';
export default function Loading() {
  return (
    <div role="status" className="flex flex-col gap-4">
      <span className="sr-only">Carregando área</span>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
