'use client';

import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

export default function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: true,
            retry: (count, error) =>
              !('status' in error && [401, 403, 409, 422].includes(Number(error.status))) &&
              count < 1,
          },
          mutations: { retry: false },
        },
      }),
  );
  useEffect(() => {
    const refresh = () => {
      void client.invalidateQueries({
        predicate: (query) =>
          [
            'personal',
            'dashboard',
            'frequency',
            'food',
            'nutrition-targets',
            'day-review',
            'daily-analysis',
          ].includes(String(query.queryKey[0])),
      });
    };
    const clear = () => {
      void client.cancelQueries();
      client.clear();
    };
    window.addEventListener('ascentiq-personal-changed', refresh);
    window.addEventListener('ascentiq-session-expired', clear);
    return () => {
      window.removeEventListener('ascentiq-personal-changed', refresh);
      window.removeEventListener('ascentiq-session-expired', clear);
      client.clear();
    };
  }, [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
