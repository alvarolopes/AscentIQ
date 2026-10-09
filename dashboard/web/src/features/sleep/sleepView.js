export const sleepDuration = (minutes) =>
  minutes == null
    ? 'Sem dado'
    : `${Math.floor(Math.round(minutes) / 60)}h${String(Math.round(minutes) % 60).padStart(2, '0')}`;

export function sleepDays(records, from, to) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to) || from > to) return [];
  const indexed = new Map(records.map((row) => [row.date, row]));
  const rows = [];
  for (
    let current = new Date(from + 'T12:00:00Z');
    current <= new Date(to + 'T12:00:00Z');
    current.setUTCDate(current.getUTCDate() + 1)
  ) {
    const day = current.toISOString().slice(0, 10),
      record = indexed.get(day);
    rows.push({
      ...record,
      date: day,
      recorded: !!record,
      hours: record?.duration_minutes == null ? null : record.duration_minutes / 60,
    });
  }
  return rows;
}

export function sleepAverage(rows, field) {
  const values = rows
    .map((row) => row[field])
    .filter((value) => value != null && Number.isFinite(value));
  return {
    value: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
    count: values.length,
  };
}
