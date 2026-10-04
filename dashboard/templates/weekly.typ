#let data = json("training-report.json")
#let take(items, count) = items.slice(0, calc.min(count, items.len()))
#let ink = rgb("#20352e")
#let accent = rgb("#126a61")
#set document(title: "AscentIQ | Relatório de treinos", author: if data.athlete.name == none { () } else { data.athlete.name })
#set page(paper: "a4", margin: 18mm, numbering: "1", footer: context align(right)[AscentIQ · Treinos · #counter(page).display()])
#set text(font: "DejaVu Sans", size: 9pt, fill: ink, lang: "pt")
#set heading(numbering: none)
#show heading.where(level: 1): it => block(above: 15pt, below: 8pt)[#text(size: 18pt, fill: accent, weight: "bold", it.body)]
#let val(x) = if x == none { "Sem dado" } else { str(x) }
#let metric(title, value, detail) = block(fill: rgb("#eeeee6"), inset: 12pt, radius: 5pt, width: 100%)[
  #text(size: 8pt, title) #parbreak()
  #text(size: 24pt, weight: "bold", val(value)) #parbreak()
  #text(size: 7pt, detail)
]
#text(size: 10pt, fill: accent, tracking: 2pt)[ASCENTIQ / ATHLETE INTELLIGENCE]
#v(8pt)
#text(font: "DejaVu Serif", size: 30pt)[Seu treino, em perspectiva.]
#v(8pt)
*#val(data.athlete.name)* · Base até #val(data.freshness.activities)

Gerado em #data.generated_at. Janela móvel de 7 dias: #data.week.start a #data.week.end.

Modelo: #data.model_version. PDF exclusivo de treinos e carga de treinamento.

Objetivo de endurance: #val(data.athlete.current_goal).

#if data.at("sync_warnings", default: ()).len() > 0 [
  #block(fill: rgb("#fff0df"), inset: 10pt)[*Atualização parcial* #parbreak() #data.sync_warnings.join(" ")]
]
= Carga e performance
#let summary = data.performance.summary
#grid(columns: (1fr, 1fr, 1fr), gutter: 8pt,
  metric("FITNESS", summary.at("fitness", default: none), "Carga crônica / 42 dias"),
  metric("FADIGA", summary.at("fatigue", default: none), "Carga aguda / 7 dias"),
  metric("FORMA", summary.at("form", default: none), "Fitness menos fadiga"))
#v(10pt)
#if data.performance.series.len() > 0 {
  image("performance.svg", width: 100%)
} else [Sem série de carga disponível. Registre ou importe atividades para construir o histórico.]
#for note in data.insights [#text(size: 8pt)[• #note] #parbreak()]
= Os últimos 7 dias
#if data.week.activity_count == 0 and data.week.strength_sessions == 0 [
  Sem atividades registradas nesta janela. Ausência de registro não comprova descanso.
] else [
  #table(columns: (1fr, 1fr, 1fr, 1fr), inset: 8pt, stroke: 0.4pt + rgb("#d8d9cd"),
    [Corrida], [D+ corrida], [Força], [Séries de trabalho],
    [#data.week.running_km km], [#data.week.running_elevation_m m], [#data.week.strength_sessions sessões], [#data.week.working_sets])

  Volume registrado de força: #data.week.strength_volume_kg kg·repetições.
]

#pagebreak()
= Corridas recentes
#if data.activities.filter(x => x.kind == "running").len() == 0 [Sem corridas registradas.]
#table(columns: (auto, 2fr, auto, auto, auto, auto), inset: 5pt, stroke: 0.4pt + rgb("#d8d9cd"),
  table.header([Data], [Atividade], [km], [Tempo], [FC média], [D+ / m]),
  ..take(data.activities.filter(x => x.kind == "running"), 20).map(x => (
    [#x.date], [#x.name], [#val(x.distance_km)], [#val(x.elapsed_time)], [#val(x.avg_hr)], [#val(x.elevation_gain_m)]
  )).flatten())
#pagebreak()
= Diário de força
#if data.strength.len() == 0 [Sem sessões de força registradas.]
Últimas seis sessões consolidadas. Aquecimentos são identificados separadamente quando disponíveis.

#for workout in take(data.strength, 6) [
  == #workout.date · #workout.title
  Duração: #val(workout.duration) · #val(workout.working_sets) séries de trabalho · #val(workout.volume_kg) kg·repetições.

  #if workout.exercises.len() == 0 [Sem séries correspondentes do Hevy para esta sessão.]
  #for exercise in workout.exercises [
    *#exercise.name* · carga máxima #val(exercise.max_weight_kg) kg

    #table(columns: (auto, 2fr, 1fr, 1fr, 1fr), inset: 5pt, stroke: 0.3pt + rgb("#d8d9cd"),
      table.header([Série], [Tipo], [Carga / kg], [Repetições], [RPE]),
      ..exercise.sets.enumerate().map(pair => {
        let item = pair.at(1)
        let kind = if item.set_type == "warmup" { "Aquecimento" } else if item.set_type == "normal" { "Trabalho" } else { item.set_type }
        ([#(pair.at(0) + 1)], [#kind], [#val(item.weight_kg)], [#val(item.reps)], [#val(item.rpe)])
      }).flatten())
    #v(7pt)
  ]
]
