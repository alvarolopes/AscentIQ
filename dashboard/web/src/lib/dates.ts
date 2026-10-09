export function calendarDay(now = new Date(), timeZone = 'America/Sao_Paulo'): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

export function displayDay(day?: string | null): string {
  if (!day) return 'Sem data';
  return new Date(`${day.slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR');
}
