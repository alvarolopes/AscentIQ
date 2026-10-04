# Importações pessoais e resumo energético Garmin

Este contrato implementa os formatos P0 da SPEC. Nenhum envio aceita caminhos locais nem executa comandos, busca URLs ou chama fornecedores. O conteúdo é recebido explicitamente pela API autenticada. Uma importação é distinta de uma sincronização Garmin/Hevy.

## Serviço e persistência

`ImportService(runtime, root)` oferece:

- `import_file(format, filename, content)`: `format` é `csv`, `gpx` ou `fit`; retorna o estado consultável e `import` (recibo da operação) / `repeated`.
- `read()`: retorna `revision`, `imports`, `records` canônicos, `source_records`, `routes`, `links`, `reconciliation`, `legacy_candidates` e `suppressed_legacy_ids`.
- `reconcile(record_id, "merge", other_id)`: une duas observações de atividade; o primeiro registro/grupo conserva prioridade por campo, e campos ausentes podem vir do outro. Não soma duração, distância ou calorias. Conflitos permanecem em `conflicts`; `field_sources` identifica o registro selecionado e `field_observation_sources` identifica o recibo que forneceu o valor quando aplicável. `sources` preserva as observações originais.
- `reconcile(record_id, "unlink", other_id)`: desfaz aquele vínculo direto. Sem `other_id`, desfaz vínculos que envolvem o registro informado. `link` e `unmerge` são aliases aceitos.
- `reconcile(record_id, "keep", other_id)`: registra que o par representa atividades distintas; mantém ambas e evita repetir a mesma pendência. Uma união explícita posterior pode rever essa decisão.
- `overlay(snapshot)`: devolve uma cópia do snapshot com atividades pessoais e rotas. Uma atividade legada vinculada é suprimida pelo seu `id`, sem editar os datasets históricos. Recalcula resumos de volume da semana e o digest do contexto; curvas legadas de carga mantêm seu método e versão e não são silenciosamente recalculadas.

O nome do arquivo é apenas metadado e deve ser um nome simples com extensão correspondente, sem separadores, drive ou stream. Originais são armazenados como `<sha256>.<formato>` em `runtime/personal-imports`. O mesmo conteúdo e formato gera o mesmo recibo mesmo que o nome enviado mude. Limite: 12 MiB de conteúdo decodificado, 10.000 atividades/sessões por arquivo e 100.000 pontos GPX.

O estado usa `operational_db(runtime, "imports", root)`: SQLite local ou PostgreSQL configurado. A tabela `personal_imports_state` guarda o estado corrente e eventos `revision:<n>` transacionais. Locks de escrita impedem perda de atualizações concorrentes; as revisões preservam recibos, registros afetados e decisões de vínculo. Erros de validação não publicam recibos nem registros parciais.

Os originais, o banco operacional e os eventos fazem parte do acervo privado de backup/exportação. A migração PostgreSQL inclui a tabela operacional; originais continuam arquivos privados do runtime, não caminhos arbitrários acessíveis pela API.

## CSV de atividades

Encoding UTF-8, separador vírgula, primeira linha como cabeçalho. Campos obrigatórios:

| Campo | Contrato |
| --- | --- |
| `id` | Identificador textual estável, exclusivo na coleção pessoal CSV; não muda ao corrigir o registro |
| `date` | ISO 8601: data simples ou data/hora; incluir offset quando conhecido |
| `type` | Modalidade, por exemplo `Run`, `Walk`, `Weight Training`, `cycling` |
| `duration_seconds` | Duração não negativa em segundos |

Campos opcionais: `date_time`, `name`, `distance_km`, `elevation_gain_m`, `avg_hr`, `max_hr`, `calories`. `date_time`, quando separado, deve incluir horário e ter o mesmo dia local de `date`. Ao mudar o dia de uma atividade com horário antes conhecido, informe também o novo horário. Números usam ponto decimal. Célula vazia ou `null`/`none` significa desconhecido, sem conversão para zero. Zero explícito é conservado. Na primeira importação a ausência permanece ausente; em uma correção do mesmo `id`, valores ausentes não apagam valores conhecidos. Um nome ausente também preserva o nome anterior.

Exemplo sintético:

```csv
id,date,type,duration_seconds,name,distance_km,elevation_gain_m,avg_hr,calories
demo-run-001,2026-10-01T08:00:00-03:00,Run,1800,Corrida leve,5.0,20,135,450
demo-strength-001,2026-10-01T18:00:00-03:00,Weight Training,2700,Força,,,,
```

O mesmo `id` em arquivo posterior é uma nova observação/correção daquela atividade. Alterar o `id` cria outra origem: parecido não é suficiente para unir automaticamente. Duas linhas com o mesmo `id` no mesmo arquivo são rejeitadas. Outros cabeçalhos de fornecedores precisam de adaptadores próprios; não há tentativa silenciosa de adivinhar unidades.

## GPX de percurso

O GPX gera uma **rota**, sem evidência suficiente para afirmar que ocorreu um treino. Mesmo pontos com horário não entram nos totais de atividade, carga ou gasto. O resumo fornece distância, elevação quando presente, pontos e nome. Segmentos desconectados não recebem um trecho artificial entre si.

Distância usa cálculo geodésico esférico; ganho de elevação é a soma dos deltas positivos presentes, sem suavização. O método fica explícito e não equivale a uma altimetria oficial. Coordenadas e números inválidos, DTD e entidades externas são rejeitados. Há pelo menos dois pontos no arquivo.

## FIT de sessão

O `content` deve ser **base64 estrito** dos bytes de um `.fit`, sem prefixo `data:` e sem caminhos. O parser `fitdecode` valida a estrutura e CRC e extrai mensagens `session` realmente presentes: horário inicial, modalidade, duração, tempo em movimento, distância, ascensão, frequência cardíaca e calorias disponíveis.

Ausências continuam desconhecidas. Um arquivo sem resumo de sessão executada é rejeitado; não se inferem todas as métricas a partir de laps incompletas. Cada sessão tem identidade derivada de serial do arquivo quando presente, início, modalidade e índice da sessão. Timestamps FIT são UTC e o offset original é preservado; a aplicação deve considerar esse fuso ao apresentar o horário. O dia de origem permanece associado ao timestamp, sem inventar um horário local do dispositivo.

## Reconciliar observações

Atividades com identificadores diferentes permanecem separadas e podem aparecer como candidatas ambíguas quando dia, modalidade e duração são semelhantes. A lista é uma ajuda para revisão, não confirmação de duplicidade; o limite de 2.000 pares é informado em `reconciliation_truncated`.

Uma origem existente no snapshot pode ser referenciada como `legacy:<snapshot.id>`. O serviço não altera a união Garmin/Hevy já feita pelo pipeline nem reescreve `training_history.json`; seu escopo é vincular/desvincular arquivos pessoais entre si e com atividades legadas. O resultado informa `legacy_refs`, e o overlay exclui apenas as linhas de base correspondentes. Para trocar a origem prioritária, desfazer o vínculo e uni-lo novamente com a origem desejada primeiro.

## Energia diária Garmin

`import_garmin_mcp_snapshot.py` normaliza `daily_metrics.get_daily_summary`, `daily_summary` e equivalentes em `data/daily_energy.json`. O destino pode ser alterado com `--energy-output`, usado dentro do workspace isolado de sincronização.

```json
{
  "schema_version": 1,
  "daily": [{
    "date": "2026-10-01",
    "source": "garmin",
    "method": "wearable_total",
    "method_version": "garmin-daily-summary/v1",
    "total_kcal": 2800,
    "active_kcal": 800,
    "resting_kcal": 2000,
    "coverage": "complete",
    "total_includes_active": true,
    "total_includes_exercise": true,
    "components_non_overlapping": false
  }]
}
```

`totalKilocalories` é total, `activeKilocalories` é atividade e `bmrKilocalories` é componente de repouso. As alternativas de nome são explícitas no normalizador. Atividades e suas calorias não participam da extração diária. O total não recebe novamente o componente ativo nem calorias de exercícios. Na ausência de total, componentes são preservados como observações, sem fabricar um total pela soma.

Cobertura `complete` requer declaração explícita da origem (`coverage` ou flag booleana de completude/finalização); ausência dessa evidência é `unknown`, mesmo em um dia passado. `partial` também é conservada. Horas de cobertura, intervalos e flag de projeção só são registrados quando fornecidos. O exemplo acima pressupõe essa evidência de completude.

Uma resposta vazia, erro ou valor nulo não apaga dias nem valores anteriores. Zero verdadeiro é válido. Componentes parciais novos não redefinem a cobertura de um total anterior ausente na atualização. Correções significativas mantêm versões do registro; `raw_fields` e `field_observed_at` permitem rastrear os valores preservados.

## Janela Garmin de revisão

O capturador revisita IDs conhecidos **dentro da janela solicitada**, incluindo seus detalhes, para absorver correções. Não consulta detalhes de todo o histórico conhecido. A janela incremental é calculada pelo pipeline com overlap; `--skip-known-activities` conserva a opção antiga de buscar apenas IDs novos. Falhas de endpoints complementares continuam explícitas no snapshot e não removem observações anteriores.

## Validação sintética

```text
python -m unittest discover -s tests -p test_imports.py -v
python -m unittest discover -s tests -p test_incremental_sync.py -v
python -m unittest discover -s dashboard/tests -p test_sleep_retention.py -v
```

Os testes usam CSV, XML GPX e FIT binário com CRC criados em memória, sem credenciais, dados privados ou chamadas a plataformas.
