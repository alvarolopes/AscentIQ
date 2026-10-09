// Completely synthetic fixtures. This process never reads athlete files or calls AI providers.
import http from 'node:http';
import { createHash, randomUUID } from 'node:crypto';

const API_PORT = 18788,
  GATEWAY_PORT = 18789,
  NEXT_PORT = 18790;
const DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).format(new Date());
const before = (count) => {
  const value = new Date(DAY + 'T12:00:00Z');
  value.setUTCDate(value.getUTCDate() - count);
  return value.toISOString().slice(0, 10);
};
const timestamp = DAY + 'T16:00:00Z';
const fingerprint = 'a'.repeat(64);
const targets = {
  status: 'ready',
  kcal: 2500,
  protein_g: 200,
  carbs_g: 250,
  fat_g: 75,
  configured: true,
  source: 'ai',
  reason: 'Plano sintético para validação.',
};
const plan = {
  id: 'plan-synthetic',
  goal_id: 'goal-synthetic',
  target_kcal: 2500,
  protein_g: 200,
  carbs_g: 250,
  fat_g: 75,
  version: 1,
  effective_from: DAY,
  next_review_date: before(-1),
  reason: 'Plano sintético.',
  source: 'ai',
};
const goal = {
  id: 'goal-synthetic',
  description: 'Reduzir gordura preservando treino',
  type: 'fat_loss',
  status: 'active',
  priority: 1,
  preserve: ['strength', 'endurance'],
  target_metric: 'weight_kg',
  target_value: 85,
  created_at: timestamp,
  updated_at: timestamp,
};
const sleepDaily = Array.from({ length: 40 }, (_, index) => ({
  date: before(index),
  duration_minutes: index === 0 ? 480 : 420 + index,
  score: index === 3 ? 0 : 82,
  resting_hr: 54,
  body_battery: 68,
  respiration: 15,
  hrv_ms: 52,
  hrv_status: 'Equilibrado',
  quality: 'Bom',
}))
  .filter((row) => row.date !== before(1))
  .reverse();
const sleep = {
  daily: sleepDaily,
  summary: {
    latest_duration_daily: sleepDaily.at(-1),
    latest_scored_daily: sleepDaily.at(-1),
    last_7_days_average_duration_minutes: 450,
    last_7_days_duration_count: 6,
  },
};
const activities = [
  {
    id: 'run-today',
    date: DAY,
    name: 'Corrida sintética',
    kind: 'running',
    distance_km: 8.94,
    duration_seconds: 3600,
    elapsed_time: '1h00',
    avg_hr: 145,
    elevation_gain_m: 120,
  },
  {
    id: 'garmin-strength',
    date: DAY,
    name: 'Força Garmin',
    kind: 'strength',
    distance_km: null,
    duration_seconds: 2400,
    elapsed_time: '40min',
    avg_hr: 120,
    elevation_gain_m: null,
  },
  {
    id: 'run-previous',
    date: before(1),
    name: 'Corrida anterior',
    kind: 'running',
    distance_km: 12.6,
    duration_seconds: 4500,
    elapsed_time: '1h15',
    avg_hr: 148,
    elevation_gain_m: 160,
  },
];
const strength = [
  {
    id: 'strength-today',
    date: DAY,
    title: 'Força consolidada',
    duration: '40min',
    duration_seconds: 2400,
    volume_kg: 1040,
    working_sets: 2,
    avg_hr: 120,
    max_hr: 150,
    match_status: 'matched',
    garmin_activity_ids: ['garmin-strength'],
    exercises: [
      {
        name: 'Agachamento',
        sets: [
          { set_type: 'warmup', weight_kg: 20, reps: 10 },
          { set_type: 'normal', weight_kg: 80, reps: 8 },
        ],
      },
      { name: 'Supino', sets: [{ set_type: 'normal', weight_kg: 40, reps: 10 }] },
    ],
  },
];
const series = Array.from({ length: 200 }, (_, index) => ({
  date: before(199 - index),
  fitness: 35 + index / 10,
  fatigue: 30 + (index % 12),
  form: 5 + index / 10 - (index % 12),
  daily_load: 30 + (index % 20),
}));
const snapshot = {
  as_of: DAY,
  generated_at: timestamp,
  athlete: { name: 'Atleta sintético' },
  freshness: { activities: DAY },
  storage: { backend: 'json' },
  sync_warnings: [],
  activities,
  strength,
  sleep,
  performance: { series, summary: series.at(-1), notes: [] },
  goals: {
    endurance: {
      status: 'active_goal',
      name: 'Prova sintética',
      target_distance_km: 21,
      event_date: before(-30),
    },
  },
  week: {
    start: before(6),
    end: DAY,
    running_km: 21.54,
    strength_sessions: 1,
    working_sets: 2,
    running_elevation_m: 280,
    activity_count: 3,
    by_kind: { running: 2, strength: 1 },
  },
  body: {
    current: { weight_kg: 90, body_fat_pct: 20, lean_mass_kg: 72 },
    reference_date: DAY,
    history: [],
  },
  race_index: {
    entries: [
      {
        id: 'race-synthetic',
        name: 'Prova histórica sintética',
        date: before(30),
        elapsed_time: '2h00',
        performance_execution_index: 80,
        confidence: 'moderada',
      },
    ],
    generated_at: timestamp,
  },
};
const sessions = new Map();

function meal(index, date = DAY) {
  return {
    id: `meal-${date}-${index}`,
    date,
    meal: ['Café da manhã', 'Almoço', 'Lanche', 'Jantar'][index % 4],
    text: `Refeição sintética ${index + 1}`,
    source: 'ai_estimated',
    created_at: timestamp,
    analysis: {
      items: [{ name: 'Alimento sintético', kcal: 400, protein_g: 20, carbs_g: 50, fat_g: 8 }],
      notes: 'Porção de teste.',
    },
  };
}
function newState() {
  return {
    revision: 1,
    diaries: new Map([
      [
        DAY,
        {
          revision: 1,
          entries: [0, 1, 2, 3].map((index) => meal(index)),
          completeness: 'partial',
          fasting_declared: false,
        },
      ],
      [
        before(46),
        {
          revision: 1,
          entries: [0, 1, 2, 3].map((index) => meal(index, before(46))),
          completeness: 'partial',
          fasting_declared: false,
        },
      ],
    ]),
    profile: {
      sex: 'male',
      height_cm: 180,
      birth_date: '1990-01-01',
      time_zone: 'America/Sao_Paulo',
    },
    checkins: [],
    measurements: [{ id: 'weight-synthetic', date: DAY, weight_kg: 90 }],
    goals: [structuredClone(goal)],
    plans: [structuredClone(plan)],
    answers: [],
    dailyReports: new Map(),
    tokens: new Map(),
    pendingAttempts: new Set(),
    conflictAttempts: new Set(),
  };
}
function getDiary(state, date) {
  if (!state.diaries.has(date))
    state.diaries.set(date, {
      revision: 1,
      entries: [],
      completeness: 'empty',
      fasting_declared: false,
    });
  return state.diaries.get(date);
}
function diaryResponse(state, date) {
  const diary = getDiary(state, date),
    totals = { kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
  let pending = 0;
  for (const entry of diary.entries) {
    if (!entry.analysis) pending++;
    for (const item of entry.analysis?.items || [])
      for (const key of Object.keys(totals))
        if (item[key] != null) totals[key] += Number(item[key]);
  }
  return {
    ...structuredClone(diary),
    totals,
    pending_count: pending,
    configured: true,
    provider: 'ollama',
    model: 'synthetic-ai',
    targets,
  };
}
function personal(state, date) {
  const food = diaryResponse(state, date);
  return {
    state: {
      revision: state.revision,
      profile: state.profile,
      preferences: { auto_nutrition_targets: true, ai_daily_limit: 20 },
      checkins: state.checkins,
      measurements: state.measurements,
      goals: state.goals,
      plans: state.plans,
      proposals: [],
      energy_records: [],
    },
    summary: {
      profile: state.profile,
      active_goal: state.goals[0],
      active_plan: state.plans[0],
      progress: {},
      coverage: { food_complete_days: 0 },
      proposals: [],
      energy: {
        registered_kcal: food.totals.kcal,
        intake_status: food.completeness,
        pending_count: food.pending_count,
        method: 'personal_energy_mifflin_v1',
        source: 'profile_model',
        coverage_basis: 'modeled_full_day',
        components: { total_kcal: 2800 },
        alternatives: [],
        limitations: ['Referência sintética.'],
      },
    },
    nutrition_targets: targets,
  };
}
function frequency(state, year) {
  const days = [];
  for (
    let day = new Date(`${year}-01-01T12:00:00Z`);
    day.getUTCFullYear() === year;
    day.setUTCDate(day.getUTCDate() + 1)
  ) {
    const date = day.toISOString().slice(0, 10),
      diary = diaryResponse(state, date),
      night = sleepDaily.find((row) => row.date === date),
      runs = activities.filter((row) => row.date === date && row.kind === 'running'),
      lifts = strength.filter((row) => row.date === date);
    const count =
      Number(Boolean(night)) +
      Number(diary.entries.length > 0) +
      Number(runs.length > 0) +
      Number(lifts.length > 0);
    days.push({
      date,
      count,
      sleep_minutes: night?.duration_minutes ?? null,
      sleep_count: Number(Boolean(night)),
      meal_count: diary.entries.length,
      kcal: diary.entries.length ? diary.totals.kcal : null,
      pending_count: diary.pending_count,
      running_count: runs.length,
      running_km: runs.length ? runs.reduce((sum, row) => sum + row.distance_km, 0) : null,
      strength_count: lifts.length,
    });
  }
  return { year, days };
}
function pagination(rows, query) {
  const page = Math.max(1, Number(query.get('page') || 1)),
    pageSize = Number(query.get('page_size')) === 15 ? 15 : 10;
  return {
    rows: rows.slice((page - 1) * pageSize, page * pageSize),
    pagination: {
      page,
      page_size: pageSize,
      pages: Math.max(1, Math.ceil(rows.length / pageSize)),
      total: rows.length,
    },
  };
}
function json(response, value, status = 200, headers = {}) {
  response.writeHead(status, {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    ...headers,
  });
  response.end(JSON.stringify(value));
}
async function body(request) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > 40 * 1024 * 1024) throw new Error('Synthetic request too large');
    chunks.push(chunk);
  }
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {};
}

const api = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://127.0.0.1'),
      path = url.pathname.replace(/^\/api\//, '');
    if (
      request.method === 'POST' &&
      (request.headers['x-ascentiq-request'] !== '1' ||
        (request.headers.origin && new URL(request.headers.origin).host !== request.headers.host))
    )
      return json(response, { detail: 'Origem ou header inválido.' }, 403);
    if (path === 'health') return json(response, { status: 'ok', synthetic: true });
    if (path === 'auth/login' && request.method === 'POST') {
      const input = await body(request);
      if (input.username !== 'synthetic' || input.password !== 'synthetic-password')
        return json(response, { detail: 'Usuário ou senha incorretos.' }, 401);
      const token = randomUUID();
      sessions.set(token, newState());
      return json(response, { username: 'synthetic' }, 200, {
        'Set-Cookie': `ascentiq_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600`,
      });
    }
    const token = request.headers.cookie
        ?.split(';')
        .map((value) => value.trim())
        .find((value) => value.startsWith('ascentiq_session='))
        ?.slice('ascentiq_session='.length),
      state = sessions.get(token);
    if (!state) return json(response, { detail: 'Sessão expirada.' }, 401);
    if (path === 'auth/session') return json(response, { username: 'synthetic' });
    if (path === 'auth/logout' && request.method === 'POST') {
      sessions.delete(token);
      return json(response, { ok: true }, 200, {
        'Set-Cookie': 'ascentiq_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0',
      });
    }
    if (path === 'dashboard') return json(response, snapshot);
    if (path === 'jobs') return json(response, { jobs: [], schedule: 'Fixture isolada.' });
    if (path === 'personal')
      return json(response, personal(state, url.searchParams.get('day') || DAY));
    if (path === 'frequency')
      return json(
        response,
        frequency(state, Number(url.searchParams.get('year') || DAY.slice(0, 4))),
      );
    if (path.startsWith('nutrition-targets/')) return json(response, targets);
    if (path === 'ai/configuration')
      return json(response, { configured: true, provider: 'ollama', model: 'synthetic-ai' });
    if (path === 'food-library') return json(response, { recipes: [] });
    if (path.startsWith('food/')) {
      const [, date, action] = path.split('/');
      if (request.method === 'GET') return json(response, diaryResponse(state, date));
      const input = await body(request),
        diary = getDiary(state, date);
      if (input.revision != null && input.revision !== diary.revision)
        return json(
          response,
          { detail: 'O diário mudou. Consulte novamente antes de salvar.' },
          409,
        );
      if (action === 'save') {
        if (input.text.includes('[conflito]') && !state.conflictAttempts.has(input.id)) {
          state.conflictAttempts.add(input.id);
          diary.revision++;
          return json(
            response,
            { detail: 'O diário mudou. Consulte novamente antes de salvar.' },
            409,
          );
        }
        if (state.tokens.has(input.save_token))
          return json(response, { ...diaryResponse(state, date), analysis_status: 'estimated' });
        const pending = input.text.includes('[pendente]') && !state.pendingAttempts.has(input.id);
        state.pendingAttempts.add(input.id);
        const entry = {
          id: input.id,
          date,
          meal: input.meal,
          text: input.text,
          source: pending ? 'ai_pending' : 'ai_estimated',
          created_at: timestamp,
          analysis: pending
            ? null
            : {
                items: [
                  {
                    name: 'Estimativa sintética',
                    kcal: 500,
                    protein_g: 35,
                    carbs_g: 40,
                    fat_g: 15,
                  },
                ],
                notes: 'Porção de teste.',
              },
        };
        diary.entries = diary.entries.filter((row) => row.id !== input.id).concat(entry);
        diary.revision++;
        state.revision++;
        state.tokens.set(input.save_token, input.id);
        return json(response, {
          ...diaryResponse(state, date),
          analysis_status: pending ? 'pending' : 'estimated',
          ...(pending ? { analysis_error: 'IA sintética temporariamente indisponível.' } : {}),
        });
      }
      if (action === 'remove') {
        diary.entries = diary.entries.filter((row) => row.id !== input.id);
        diary.revision++;
        state.revision++;
        return json(response, diaryResponse(state, date));
      }
      if (action === 'coverage') {
        diary.completeness = input.completeness;
        diary.fasting_declared = Boolean(input.fasting_declared);
        diary.revision++;
        state.revision++;
        return json(response, diaryResponse(state, date));
      }
    }
    if (path.startsWith('personal/') && request.method === 'POST') {
      const [, kind, action] = path.split('/'),
        input = await body(request);
      if (input.revision != null && input.revision !== state.revision)
        return json(response, { detail: 'Os dados mudaram.' }, 409);
      if (kind === 'profile') state.profile = input.value;
      else if (Array.isArray(state[kind])) {
        if (action === 'remove') state[kind] = state[kind].filter((row) => row.id !== input.id);
        else
          state[kind] = state[kind]
            .filter((row) => row.id !== input.record.id)
            .concat({
              ...input.record,
              id: input.record.id || randomUUID(),
              updated_at: timestamp,
            });
      }
      state.revision++;
      return json(response, { state: personal(state, DAY).state });
    }
    if (path === 'assistant/context') {
      const includeMedical = url.searchParams.get('include_medical') === 'true',
        selectedDay = url.searchParams.get('day') || DAY;
      return json(response, {
        configured: true,
        fingerprint,
        prompt: `Contexto sintético: alimentação, treino e sono.${includeMedical ? ' SYNTHETIC_MEDICAL_PRIVATE' : ''}`,
        context: {
          period: { from: selectedDay, to: selectedDay },
          selection: {
            meal_details_included: 4,
            meal_detail_count: 4,
            activities_included: 1,
            activity_count: 1,
            strength_details_included: 1,
            strength_detail_count: 1,
          },
          ...(includeMedical ? { medical: 'SYNTHETIC_MEDICAL_PRIVATE' } : {}),
        },
      });
    }
    if (path === 'assistant/history') {
      const conversation = url.searchParams.get('conversation_id'),
        selected = state.answers
          .filter((row) => !conversation || row.conversation_id === conversation)
          .slice()
          .reverse(),
        paged = pagination(selected, url.searchParams);
      return json(response, { history: paged.rows, pagination: paged.pagination });
    }
    if (path === 'assistant' && request.method === 'POST') {
      const input = await body(request),
        answer = {
          id: randomUUID(),
          conversation_id: input.conversation_id,
          date: input.day,
          created_at: timestamp,
          model: 'synthetic-ai',
          source: input.manual_response ? 'imported' : 'ai_generated',
          question: input.question,
          text:
            input.manual_response ||
            'Você registrou alimentação, corrida e força. Continue acompanhando seu objetivo.',
          include_medical: Boolean(input.include_medical),
          withheld_medical_turns:
            !input.include_medical && state.answers.some((row) => row.include_medical),
        };
      state.answers.push(answer);
      return json(response, answer);
    }
    if (path.startsWith('daily-analysis/')) {
      const date = path.split('/')[1];
      const dailyStrength = strength.filter((row) => row.date === date);
      const linked = new Set(dailyStrength.flatMap((row) => row.garmin_activity_ids || []));
      const dailyActivities = activities.filter((row) => row.date === date && !linked.has(row.id));
      const context = {
        session_count: dailyActivities.length + dailyStrength.length,
        activities: dailyActivities,
        strength: dailyStrength,
        sleep,
      };
      const analysisFingerprint = createHash('sha256')
        .update(`synthetic-analysis:${date}`)
        .digest('hex');
      const prompt = `Analise apenas o contexto sintético de ${date}.`;
      if (request.method === 'POST') {
        const input = await body(request);
        if (input.fingerprint !== analysisFingerprint)
          return json(
            response,
            { detail: 'Os treinos mudaram. Consulte o contexto novamente.' },
            409,
          );
        if (!context.session_count)
          return json(response, { detail: 'Não há treinos registrados para esta data.' }, 422);
        const imported = input.text !== undefined;
        if (imported && (typeof input.text !== 'string' || input.text.trim().length < 20))
          return json(response, { detail: 'A resposta importada é muito curta.' }, 422);
        const report = {
          day: date,
          fingerprint: analysisFingerprint,
          source: imported ? 'imported' : 'ollama',
          model: imported ? 'Resposta importada' : 'synthetic-ai',
          text: input.text || 'O treino combinou endurance e força. Priorize recuperação.',
          prompt,
          context,
          generated_at: timestamp,
        };
        state.dailyReports.set(date, report);
        return json(response, report);
      }
      return json(response, {
        configured: true,
        fingerprint: analysisFingerprint,
        prompt,
        context,
        report: state.dailyReports.get(date) || null,
        stale: false,
      });
    }
    if (path.startsWith('day-review/')) {
      const report = {
        context: { user_report: '', facts_summary: 'Dia sintético com refeições e treinos.' },
        text: 'Seu dia combina treinos e alimentação registrada.',
        prompt: 'Analise o contexto sintético.',
        generated_at: timestamp,
        model: 'synthetic-ai',
      };
      if (request.method === 'POST') {
        const input = await body(request);
        report.context.user_report = input.notes;
      }
      return json(response, { configured: true, report, stale: false });
    }
    if (path === 'integrations')
      return json(response, { providers: [], status: {}, configured: {} });
    if (path === 'documents') return json(response, { documents: [] });
    return json(response, { detail: `Fixture não implementada: ${request.method} ${path}` }, 404);
  } catch (error) {
    json(response, { detail: String(error) }, 500);
  }
});

// Same routing contract as nginx.conf; no Origin relaxation in the fixture API.
const gateway = http.createServer((request, response) => {
  const apiRequest = request.url.startsWith('/api/');
  const upstream = http.request(
    {
      hostname: '127.0.0.1',
      port: apiRequest ? API_PORT : NEXT_PORT,
      path: request.url,
      method: request.method,
      headers: { ...request.headers, host: request.headers.host, 'x-forwarded-proto': 'http' },
    },
    (incoming) => {
      response.writeHead(incoming.statusCode || 502, incoming.headers);
      incoming.pipe(response);
    },
  );
  upstream.on('error', () => {
    if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'text/plain' });
    response.end('Synthetic upstream unavailable');
  });
  request.on('aborted', () => upstream.destroy());
  request.pipe(upstream);
});
api.listen(API_PORT, '127.0.0.1');
gateway.listen(GATEWAY_PORT, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => {
    api.close();
    gateway.close();
    setTimeout(() => process.exit(0), 300).unref();
  });
console.log(`Synthetic API ${API_PORT}; same-origin gateway ${GATEWAY_PORT}; Next ${NEXT_PORT}.`);
