# Requisitos, aceitação e evidências

Referência: [SPEC_PLATAFORMA_SAUDE_FITNESS.md](../SPEC_PLATAFORMA_SAUDE_FITNESS.md), RF-01–RF-30 e A01–A39. Este mapa distingue código/teste disponível de prova operacional. Registra o escopo dos testes, da revisão móvel e da recuperação exercitada; não certifica integração autenticada com fornecedores nem recomendação clínica.

## Resultado de execução conhecido

Atualização de 05/10/2026: o botão de análise do dia em Hoje e Alimentação tem cobertura em `test_day_review.py` e `test_personal_api.py` para horário, diário parcial/desconhecido, planejamento, consolidação, privacidade, cache, concorrência de leituras, falhas e bloqueio de API paga. A análise mantém planos/registros e torna o prompt consultável. As heurísticas não são critérios clínicos; veja [DAY_REVIEW.md](DAY_REVIEW.md).

Atualização de 05/10/2026: metas diárias com Ollama, histórico, pausa, concorrência e indicadores de consumo/meta têm cobertura em `test_nutrition_targets.py` e `test_personal_api.py`. A inferência real e a apresentação na alimentação foram conferidas em um container descartável com perfil, treinos e refeição fictícios. O serviço preserva a última meta em falhas e identifica dados insuficientes. Método e limites: [NUTRITION_TARGETS.md](NUTRITION_TARGETS.md). As evidências anteriores abaixo conservam suas datas e escopos.

Evidências disponíveis em 03/10/2026, com fontes sintéticas para as suítes:

- Rodada final completa em ambiente com PostgreSQL descartável: **105 testes de `dashboard/tests` e 28 testes de `tests`, total de 133 testes Python aprovados, sem testes ignorados**. Os 28 incluem 21 de importações e 7 de sincronização incremental. Cobrem migrações, persistência operacional, concorrência, FIT válido com CRC, GPX como rota, vínculos reversíveis, energia Garmin e ordem temporal dos snapshots.
- As regressões finais incluem diário legado, upload inválido, credenciais, reconstrução vazia, cache concorrente e quota da IA no fuso pessoal; os 12 casos de API incluem original de documento ausente e consentimentos textuais rejeitados sem chamada ao fornecedor. Esses testes fazem parte da rodada Python final e não são somados novamente.
- **3 testes Node aprovados** e frontend compilado no build Docker. Builds das imagens API e web aprovados. Build é evidência de empacotamento e não comprova acesso a fornecedores.
- O runner `dashboard/tests/empty_installation_smoke.py` validou instalação PostgreSQL vazia, inicialização idempotente, autenticação e ausência de atividades, perfil, metas e déficit inventados.
- **Dois relatórios gerados com o compilador Typst real**, incluindo um relatório de primeira instalação vazia. Essa execução comprova a geração dos artefatos nesses cenários, sem validar conclusões clínicas nem todos os possíveis conteúdos/layouts.
- Produção atualizada com API/web em `http://localhost:8787`: **10 endpoints autenticados responderam 200** e os dados anteriores foram preservados. O smoke autenticado não comprova chamadas aos fornecedores remotos.
- Inspeção visual manual em viewport de **390 px**: Hoje, alimentação, perfil, objetivos e assistente passaram sem overflow horizontal. Não cobre toda a interface, todos os teclados ou estados de erro.
- Backup novo após a atualização: **1.399 arquivos verificados**, com ensaio de `restore-test` concluído: dump restaurado em PostgreSQL temporário, revisão ativa e todos os bytes dos datasets comparados, com `verified: true`, `postgres_restore: true`, `byte_exact: true`. O banco temporário foi removido após a verificação. O backup anterior, com 1.387 arquivos, também havia passado pelo mesmo ensaio. Essas verificações não iniciaram toda a aplicação com runtime e anexos restaurados em uma instalação nova.
- A IA remota permaneceu sem chave configurada e não foi chamada. Conexões autenticadas e respostas reais dos fornecedores remotos continuam sem verificação nesta entrega; registro manual, contexto exportado e resposta importada têm evidência sintética.

As suítes usam arquivos/SQLite temporários e PostgreSQL descartável. Testes de API usam autenticação e respostas simuladas; não enviam os dados privados do projeto a um fornecedor. A verificação operacional de backup indicada acima é uma evidência distinta dos testes sintéticos.

Os comandos reproduzíveis são:

```text
python -B -m pytest dashboard/tests tests -q
```

O ambiente deve ter as dependências de projeto/dashboard. Os testes exigem um PostgreSQL **descartável** via `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` (o `PGDATABASE` precisa começar com `ascentiq_test_` e o usuário precisa de `CREATEDB`); nunca apontar a suíte de integração para a base pessoal de produção. O build de frontend e a revisão visual são evidências separadas da suíte Python.

## Mapa dos requisitos funcionais

Os arquivos de teste na tabela ficam em `dashboard/tests`, exceto `tests/test_imports.py` e `tests/test_incremental_sync.py`.

| Requisito | Implementação | Evidência automatizada / limite |
| --- | --- | --- |
| RF-01 Perfil editável | HealthStore, API pessoal, interface de perfil | `test_health.py`, `test_personal_api.py`: validação, revisão e vigência |
| RF-02 Preferências/restrições | Estado pessoal versionado e interface | Validação e efeito de prioridade/preservação; restrições declaradas não se tornam diagnóstico |
| RF-03 Memória contextual | Perfil/objetivos/plano/decisões com versões; assistente | Testes históricos e de mudança de objetivo em `test_health.py` / `test_personal_api.py` |
| RF-04 Conectar/importar | Configurações privadas, pipeline, ImportService | `test_imports.py`, `test_product_support.py`; autenticação externa real pendente |
| RF-05 Incremental confiável | Capturadores, importer, jobs e rollback por fonte | `test_incremental_sync.py`, `test_repository.py`, `test_sleep_retention.py` |
| RF-06 Consolidação | Consolidação Garmin/Hevy e vínculos pessoais reversíveis | `test_strength_consolidation.py`, `test_dashboard.py`, `test_imports.py` |
| RF-07 Diário multimodal | Snapshot e overlay de atividades | Tipos, métricas ausentes, sessões e importações em `test_dashboard.py` / `test_imports.py` |
| RF-08 Evolução | Filtros, resumo semanal, séries de carga e histórico | Cálculos de período testados; interpretações comparativas visuais requerem inspeção |
| RF-09 Carga/recuperação | Modelo legado versionado e sinais de contexto | `test_dashboard.py`, `test_sleep.py`; importações pessoais não recalculam automaticamente curvas legadas |
| RF-10 Sono | Dataset preservado, normalização e painel | `test_sleep.py`, `test_sleep_retention.py` |
| RF-11 Medidas | Medidas datadas, métodos e tendências | `test_health.py`, `test_personal_api.py`, `test_dashboard.py` |
| RF-12 Check-ins | Registro pessoal com escalas e notas | Validação e influência na revisão em `test_health.py` |
| RF-13 Documentos/saúde | Acervo e uploads privados, extração revisável | `test_product_support.py`, `test_personal_api.py`; extração real de IA pendente |
| RF-14 Diário alimentar | FoodDiary e interface/API | `test_nutrition.py`, `test_product_support.py`, `test_personal_api.py` |
| RF-15 Estimativa | Validação, origem/notas, manual/importado e IA opcional | Contratos numéricos e fluxo simulado testados; precisão da estimativa real não certificada |
| RF-16 Cobertura alimentar | Estado do dia e pendências numéricas | `test_health.py`, `test_product_support.py`, `test_personal_api.py` |
| RF-17 Gasto | Totais canônicos, modelo de perfil e Garmin daily | `test_health.py`, `test_imports.py`; cobertura real disponível depende da origem |
| RF-18 Balanço | Contabilidade determinística e dias utilizáveis | `test_health.py`: parcialidade, projeção, ausência e não duplicação |
| RF-19 Objetivos | Cadastro, prioridade, estado, indicadores e versões | `test_health.py`, `test_personal_api.py` |
| RF-20 Plano | Plano inicial/provisório, metas e vigência | `test_a35_empty_installation_initial_and_provisional_plan` e API |
| RF-21 Adaptação | Política transparente baseada em evidência | Casos A21/A36, conflitos e recuperação em `test_health.py` |
| RF-22 Decisões | Aceite/rejeição, versões e revalidação de proposta | Casos A36/A37 e decisão histórica em `test_health.py` / API |
| RF-23 IA contextual | Escopo selecionado e totais fora da resposta textual | `test_daily_analysis.py`, `test_personal_api.py` |
| RF-24 Análises datadas | Contexto/período/fingerprint e histórico | Cache, erro, resposta importada e exclusão de futuro testados |
| RF-25 Assistente | Pergunta com contexto e histórico de respostas | `test_personal_api.py`, `test_backend_safety.py`: cache concorrente e quota local; qualidade conversacional real requer validação |
| RF-26 Interface | Áreas responsivas, formulários e estados explícitos | Fluxos API cobertos; cinco áreas revisadas manualmente em 390 px sem overflow; jornada/teclado completos pendentes |
| RF-27 Rastreabilidade | Datasets/revisões operacionais/originais/fingerprints | `test_repository.py`, `test_health.py`, `test_imports.py`, `test_product_support.py` |
| RF-28 Controle dos dados | Autenticação, escopo, credenciais cifradas e desconexão | `test_dashboard.py`, `test_product_support.py`, `test_personal_api.py`; política de retenção deve acompanhar operação |
| RF-29 Continuidade | Backup cifrado, hashes e recuperação PostgreSQL | Backup novo com 1.399 arquivos íntegros e restauração PostgreSQL byte a byte; inicialização integral em nova instalação pendente |
| RF-30 Portabilidade | JSON e ZIP com dados e anexos selecionados | `test_export_excludes_credentials_and_contains_user_data`, `test_export_archive.py`; leitura independente do pacote ainda pendente |

## Mapa dos cenários de aceitação

“Sintético” indica cenário automatizado reproduzível; pode envolver mocks de fornecedores. “Parcial” indica que uma parte tem evidência e o restante exige uma verificação específica.

| Cenário | Evidência correspondente | Cobertura/limite |
| --- | --- | --- |
| A01 Usuário novo | API perfil/objetivo; CSV manual; testes de instalação vazia | Sintético; conexão autenticada real pendente |
| A02 Histórico incompleto | `test_missing_not_zero`; pendências/ausência em health | Sintético |
| A03 Importação repetida | `test_repeated_csv_is_one_receipt_record_and_original`; API import repeat | Sintético |
| A04 Garmin + Hevy | `test_hevy_link_one_consolidated_session`; força consolidada | Sintético; energia diária testada separadamente |
| A05 Ambiguidade | `test_ambiguous_activities_remain_separate_until_merge_and_can_unlink`; decisão `keep` | Sintético |
| A06 Falha de fonte | `test_failed_provider_restores_sleep_and_activities` | Sintético |
| A07 Sono corrigido | `test_partial_response_preserves_old_dates_fields_and_zero` | Sintético |
| A08 Refeição com IA | Validação/importação alimentar e fluxo API de análise revisada | Sintético e área alimentar revisada em 390 px; chamada real pendente |
| A09 Porção desconhecida | Notas/hipóteses do contrato, registro alimentar pendente | Parcial: testar resposta de IA real ambígua sem falsa certeza |
| A10 Correção alimentar | `test_food_pending_complete_edit_stale_restore_and_retry` | Sintético |
| A11 Repetir salvamento | `test_roundtrip_totals_retry_and_remove`; conflito/retry do diário | Sintético |
| A12 Diário parcial | `test_missing_partial_and_pending_intake_do_not_prove_deficit` | Sintético |
| A13 Nenhuma refeição | `test_empty_day_requires_explicit_fasting_and_removal_reopens_coverage` | Sintético |
| A14 Exercício incluído | `test_a14_total_includes_exercise_without_duplicate`; Garmin daily total | Sintético |
| A15 Gasto ausente | Ausência de perfil/gasto e estado parcial em `test_health.py` | Sintético |
| A16 Dia em andamento | `_energy` distingue projeção e cobertura; testes de energia | Parcial: conferir rótulos/intervalos em tela durante dia real |
| A17 Semana com lacunas | Contagens/somas de dias utilizáveis em health | Sintético; não extrapola a semana |
| A18 Medida antiga | `test_body_date_and_unknown_recovery`; contexto histórico do assistente | Sintético |
| A19 Metas concorrentes | `test_recovery_or_competing_goal_prevents_restriction` | Sintético |
| A20 Um ponto isolado | Janela, número de datas e abrangência mínima em revisão | Sintético via cenário de evidência insuficiente |
| A21 Revisão limitada | `test_a21_insufficient_evidence_preserves_plan` | Sintético |
| A22 Decisão/rejeição | `test_rejection_does_not_publish_plan_and_same_review_is_idempotent`; A36 | Sintético |
| A23 Meta concluída | Objetivos/estados históricos; `test_goal_archive_edit_and_remove_preserve_historical_versions` | Sintético para motor; conferir narrativa real do assistente |
| A24 IA indisponível | Registro pendente/manual; erro/caching em daily analysis | Sintético |
| A25 Resposta inválida | `test_invalid_estimates`; contrato de provider/incomplete response | Sintético |
| A26 Análise histórica | `test_assistant_historical_context_excludes_future_plans_and_body`; perfil com vigência | Sintético |
| A27 Análise após correção | Fingerprints, cache invalidado e histórico preservado | Parcial: verificar identificação visual de análise antiga no histórico pessoal |
| A28 Privacidade | Contexto por escopo, opt-in médico e `test_textual_consent_does_not_authorize_document_or_medical_ai` | Sintético: valores textuais não autorizam envio e provider não é chamado |
| A29 Exportação | `test_export_excludes_credentials_and_contains_user_data`, `test_explicit_attachments_and_no_credentials` | JSON/ZIP e documentos selecionados testados; leitura por uma segunda implementação pendente |
| A30 Recuperação | `test_encrypted_backup_and_tamper_detection`; ensaio operacional de `restore-test` | Backup novo: 1.399 arquivos íntegros e dump PostgreSQL restaurado byte a byte; runtime/anexos com aplicação iniciada em ambiente novo pendentes |
| A31 Fuso/virada | CSV com offset, sono/agenda local e `test_assistant_quota_uses_personal_timezone_at_midnight` | Parcial: ampliar casos de viagem, mudança de fuso e sessão cruzando meia-noite |
| A32 Celular | API e inspeção manual de Hoje, alimentação, perfil, objetivos e assistente em 390 px | Sem overflow nessas cinco áreas; teclado/jornada de decisões, vínculos e falhas completos pendentes |
| A33 Refeição pendente | `test_legacy_diary_pending_complete_and_recovery`; API diário | Sintético |
| A34 Wearable parcial | Modo estrito e `test_partial_wearable_uses_identified_integral_model_in_auto` | Sintético: wearable continua parcial/desconhecido; alternativa de modelo tem origem e cobertura próprias |
| A35 Plano inicial | `test_a35_empty_installation_initial_and_provisional_plan` | Sintético |
| A36 Ajuste efetivo | `test_a36_trend_adjustment_requires_acceptance_and_preserves_history`, incluindo revisão posterior | Sintético |
| A37 Contexto alterado | `test_a37_food_or_goal_change_marks_proposal_stale`; API alteração corporal | Sintético |
| A38 Instalação vazia | Health/imports/API, reconstrução sem amostras, `empty_installation_smoke.py` e relatório Typst real | PostgreSQL descartável inicializado e autenticado sem fatos de base privada anterior; geração de relatório vazio exercitada |
| A39 Completo/pending kcal | `test_missing_partial_and_pending_intake_do_not_prove_deficit`; diário completo com pendências | Sintético |

## Pendências concretas de validação

1. Ensaiar recuperação integral em outro ambiente: banco, runtime, documentos, imagens alimentares, originais de importação e aplicação iniciada; verificar a equivalência além dos datasets PostgreSQL já conferidos.
2. Completar a jornada móvel com teclado, proposta, rejeição/aceite, revisão de vínculos e falhas. A ausência de overflow nas cinco áreas inspecionadas não comprova toda essa jornada.
3. Validar cada conexão externa em sessão autorizada, incluindo cobertura real de calorias, dados tardios/corrigidos e falhas. Nenhum teste simulado comprova acesso atual.
4. Validar respostas reais de IA para porções e imagens ambíguas e contexto histórico; medir custo/latência sem alterar os totais contábeis a partir de texto livre.
5. Testar leitura/migração do JSON/ZIP por uma implementação independente e seleção das diferentes classes de anexos. Exportação portável e backup têm finalidades diferentes.
6. Revisar os parâmetros adaptativos com uso observado e avaliação apropriada do domínio. O paper da fórmula de repouso não comprova a política de adaptação.

Essa lista representa limites de evidência e tarefas identificadas; não transforma mocks, verificação de arquivo ou build em certificação completa do produto.
