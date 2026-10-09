export const daysBefore = (day, count) => {
  const value = new Date(day + 'T12:00:00Z');
  value.setUTCDate(value.getUTCDate() - count);
  return value.toISOString().slice(0, 10);
};
export const activityKinds = {
  running: 'Corrida',
  strength: 'Força',
  cycling: 'Bike',
  swimming: 'Natação',
  other: 'Outros',
};

export function exerciseGroup(name) {
  const normalized = name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
  if (/abdominal|prancha|rotac|flexao lateral|joelhos nas barras/.test(normalized)) return null;
  if (
    /agachamento|abdutor|adutor|extensora|flexora|panturrilha|quadril|pelvic|perna|leg press|terra|impulso/.test(
      normalized,
    )
  )
    return 'legs';
  if (
    /ombro|desenvolvimento|shoulder|encolhimento|triceps|biceps|rosca|supino|crucifixo|voador|puxada|remada|barra fixa|fundos sentado|punho/.test(
      normalized,
    )
  )
    return 'upper';
  return null;
}

export function weeklyRunning(rows) {
  const weeks = {};
  rows.forEach((row) => {
    const offset = (new Date(row.date + 'T12:00:00Z').getUTCDay() + 6) % 7;
    const key = daysBefore(row.date, offset);
    weeks[key] = (weeks[key] || 0) + (row.distance_km || 0);
  });
  return Object.entries(weeks)
    .sort()
    .map(([date, km]) => ({ date, km }));
}

export function weeklyStrength(rows) {
  const weeks = {};
  rows.forEach((row) => {
    const key = daysBefore(row.date, (new Date(row.date + 'T12:00:00Z').getUTCDay() + 6) % 7);
    const bucket = (weeks[key] ||= { date: key, legs: 0, upper: 0 });
    row.exercises.forEach((exercise) => {
      const group = exerciseGroup(exercise.name);
      if (group)
        bucket[group] += exercise.sets.reduce(
          (sum, set) =>
            sum +
            (set.set_type === 'normal' && Number(set.weight_kg) > 0 && Number(set.reps) > 0
              ? Number(set.weight_kg) * Number(set.reps)
              : 0),
          0,
        );
    });
  });
  return Object.values(weeks)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((row) => ({ ...row, legs: Math.round(row.legs), upper: Math.round(row.upper) }));
}
