import Link from 'next/link';
import { Button } from '@/components/ui/button';
export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-lg flex-col gap-4 p-8">
      <h1 className="text-2xl font-semibold">Página não encontrada</h1>
      <Button asChild>
        <Link href="/">Abrir Dashboard</Link>
      </Button>
    </main>
  );
}
