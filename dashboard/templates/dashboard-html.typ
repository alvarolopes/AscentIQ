#let data = json("snapshot.json")
#let take(items, count) = items.slice(0, calc.min(count, items.len()))
#let val(value) = if value == none { "Sem dado" } else { str(value) }
#let el(tag, body, class: "") = html.elem(tag, attrs: (class: class), body)
#let table(headers, rows) = el("div", class: "table-wrap", html.elem("table")[
  #html.elem("thead")[#html.elem("tr")[#for head in headers { html.elem("th", head) }]]
  #html.elem("tbody")[#for row in rows { html.elem("tr")[#for cell in row { html.elem("td", val(cell)) }] }]
])
#let metric(title, value, note) = el("article", class: "metric")[
  #el("span", class: "kicker", title)
  #el("strong", class: "value", val(value))
  #el("span", class: "muted", note)
]
#html.elem("html", attrs: (lang: "pt-BR"))[
  #html.elem("head")[
    #html.elem("meta", attrs: (charset: "utf-8"))
    #html.elem("meta", attrs: (name: "viewport", content: "width=device-width,initial-scale=1"))
    #html.elem("title")[AscentIQ / Dashboard semanal]
    #html.elem("style", read("report.css"))
  ]
  #html.elem("body")[
    #el("header", class: "topbar")[
      #el("strong", "AscentIQ / ATHLETE INTELLIGENCE")
      #el("div", class: "actions")[
        #html.elem("a", attrs: (href: "/", class: "secondary"))[Voltar ao painel]
        #html.elem("a", attrs: (href: "pdf", class: "button", download: "AscentIQ-Treinos.pdf"))[Baixar PDF de treinos]
      ]
    ]
    #html.elem("main")[
      #el("section", class: "hero")[
        #el("span", class: "kicker")[DASHBOARD HTML GERADO PELO TYPST]
        #el("h1")[Resumo de treinos]
        #el("p")[#val(data.athlete.name) · Dados de treinos até #val(data.freshness.activities)]
      ]
      #if data.at("sync_warnings", default: ()).len() > 0 {
        el("aside", class: "notice", data.sync_warnings.join(" "))
      }
      #let summary = data.performance.summary
      #el("section", class: "metrics")[
        #metric("FITNESS", summary.at("fitness", default: none), "Carga crônica / 42 dias")
        #metric("FADIGA", summary.at("fatigue", default: none), "Carga aguda / 7 dias")
        #metric("FORMA", summary.at("form", default: none), "Fitness menos Fadiga")
      ]
      #el("section", class: "panel")[
        #el("h2")[Carga e adaptação / últimos 90 dias]
        #if data.performance.series.len() > 0 {
          html.elem("img", attrs: (src: "chart", alt: "Fitness, Fadiga e Forma ao longo dos últimos 90 dias", class: "chart"))
        } else {
          el("p", class: "notice")[Sem série de carga disponível. Registre ou importe atividades para construir o histórico.]
        }
        #for insight in data.insights { el("p", class: "muted small", insight) }
      ]
      #el("section", class: "panel")[
        #el("h2")[Últimos 7 dias]
        #el("p", class: "muted")[#data.week.start a #data.week.end]
        #if data.week.activity_count == 0 and data.week.strength_sessions == 0 {
          el("p", class: "notice")[Sem atividades registradas nesta janela. Ausência de registro não comprova descanso.]
        } else {
          table(("Corrida / km", "D+ corrida / m", "Sessões de força", "Séries de trabalho"), ((data.week.running_km, data.week.running_elevation_m, data.week.strength_sessions, data.week.working_sets),))
        }
      ]
      #el("section", class: "panel")[
        #el("h2")[Corridas recentes]
        #if data.activities.filter(x => x.kind == "running").len() == 0 {
          el("p", class: "muted")[Sem corridas registradas.]
        }
        #table(("Data", "Atividade", "Distância / km", "Tempo", "FC média"), take(data.activities.filter(x => x.kind == "running"), 20).map(x => (x.date, x.name, x.distance_km, x.elapsed_time, x.avg_hr)))
      ]
      #el("section", class: "panel")[
        #el("h2")[Diário de força]
        #if data.strength.len() == 0 {
          el("p", class: "muted")[Sem sessões de força registradas.]
        }
        #for workout in take(data.strength, 15) {
          html.elem("details")[
            #html.elem("summary")[#workout.date · #workout.title · #val(workout.working_sets) séries · #val(workout.volume_kg) kg·rep]
            #for exercise in workout.exercises {
              el("h3", exercise.name)
              table(("Série", "Tipo", "Carga / kg", "Repetições", "RPE"), exercise.sets.enumerate().map(pair => (pair.at(0) + 1, pair.at(1).set_type, pair.at(1).weight_kg, pair.at(1).reps, pair.at(1).rpe)))
            }
          ]
        }
      ]
      #el("section", class: "panel")[
        #el("h2")[Medidas corporais]
        #el("p", class: "notice")[Última avaliação: #val(data.body.reference_date). Não é uma medição de hoje.]
        #let body = data.body.at("current", default: (:))
        #table(("Indicador", "Valor medido"), (
          ("Peso / kg", body.at("weight_kg", default: none)),
          ("Gordura corporal / %", body.at("body_fat_pct", default: none)),
          ("Massa magra / kg", body.at("lean_mass_kg", default: none)),
          ("Cintura / cm", body.at("waist_cm", default: none)),
        ))
        #el("h3")[Histórico de medidas]
        #table(("Data", "Peso / kg", "Cintura / cm", "Gordura / %"), data.body.at("history", default: ()).map(x => (x.date, x.at("weight_kg", default: none), x.at("waist_cm", default: none), x.at("body_fat_pct", default: none))))
      ]
      #el("section", class: "panel")[
        #el("h2")[Exames e saúde / registro privado]
        #el("p", class: "notice", data.medical.disclaimer)
        #el("p", data.medical.status.at("cardiovascular_summary", default: "Sem resumo disponível."))
        #el("p", class: "muted")[Contexto da coleta: #data.medical.context.at("athlete_report", default: "Sem contexto.")]
        #for record in data.medical.records {
          html.elem("details")[
            #html.elem("summary")[#record.date · #record.label]
            #table(("Indicador / contexto", "Resultado registrado"), record.rows.map(row => (row.label, row.value)))
          ]
        }
      ]
      #el("footer")[Gerado localmente em #data.generated_at · #data.model_version · Sem LLM nos cálculos. Exportação HTML Typst experimental, com versão fixada e saída validada.]
    ]
  ]
]
