'use client';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertTitle>Não foi possível exibir esta área.</AlertTitle>
      <AlertDescription>
        <p>Seus registros continuam salvos. Tente consultar novamente.</p>
        <Button variant="outline" onClick={reset}>
          Tentar novamente
        </Button>
      </AlertDescription>
    </Alert>
  );
}
