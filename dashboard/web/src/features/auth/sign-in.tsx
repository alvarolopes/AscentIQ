'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, type LoginValues } from '@/lib/api/contracts';
import { apiRequest } from '@/lib/api/client';
import { safeReturnTo } from '@/lib/return-to';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Field, FieldGroup, FieldLabel, FieldError } from '@/components/ui/field';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Logo } from '@/components/shell/logo';

export default function SignIn({ returnTo }: { returnTo: string }) {
  const [error, setError] = useState('');
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '' },
  });
  async function submit(values: LoginValues) {
    try {
      setError('');
      await apiRequest('auth/login', values);
      window.location.replace(safeReturnTo(returnTo, window.location.origin));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Não foi possível entrar.');
    }
  }
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader className="gap-5">
          <Logo />
          <div>
            <CardTitle>Acesse seu painel</CardTitle>
            <CardDescription>Seus registros de saúde e fitness, em um só lugar.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(submit)}>
            <FieldGroup>
              <Field data-invalid={Boolean(errors.username)}>
                <FieldLabel htmlFor="username">Usuário</FieldLabel>
                <Input
                  id="username"
                  autoComplete="username"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.username)}
                  {...register('username')}
                />
                {errors.username ? <FieldError>{errors.username.message}</FieldError> : null}
              </Field>
              <Field data-invalid={Boolean(errors.password)}>
                <FieldLabel htmlFor="password">Senha</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  aria-invalid={Boolean(errors.password)}
                  {...register('password')}
                />
                {errors.password ? <FieldError>{errors.password.message}</FieldError> : null}
              </Field>
              {error ? (
                <Alert variant="destructive" role="alert">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Entrando…' : 'Entrar'}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
