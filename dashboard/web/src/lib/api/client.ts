export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T = unknown>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    ...(body !== undefined
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-AscentIQ-Request': '1' },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('auth/login'))
      window.dispatchEvent(new Event('ascentiq-session-expired'));
    const detail =
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : response.status === 409
          ? 'Os dados mudaram. Consulte novamente antes de salvar.'
          : response.status === 401
            ? 'Entre novamente para acessar seus dados.'
            : 'Não foi possível concluir. Confira os campos e tente novamente.';
    throw new ApiError(detail, response.status);
  }
  if (body !== undefined && !path.startsWith('auth/'))
    window.dispatchEvent(new Event('ascentiq-personal-changed'));
  return payload as T;
}
