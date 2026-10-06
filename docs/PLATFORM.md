# Plataforma individual — funcionamento e decisões atuais

Referência de produto: [SPEC_PLATAFORMA_SAUDE_FITNESS.md](../SPEC_PLATAFORMA_SAUDE_FITNESS.md). Este documento explica a implementação que amplia o portal existente. A SPEC continua permitindo uma reconstrução com outras tecnologias. Os métodos abaixo descrevem regras do software, não uma prescrição pessoal ou validação clínica.

## Ciclo entregue pelos módulos

1. Registrar perfil, preferências e objetivos; conectar uma fonte ou importar atividades.
2. Guardar observações, reconhecer lacunas e revisar possíveis duplicatas.
3. Registrar alimentação por descrição ou foto; salvar calcula e registra automaticamente a estimativa de calorias e nutrientes.
4. Declarar a cobertura alimentar; calcular gasto e balanço apenas com entradas utilizáveis.
5. Acompanhar medidas, treino, sono e check-ins; atualizar metas alimentares diariamente com IA local quando a opção estiver ativa.
6. Avaliar a proposta, aceitar/rejeitar e acompanhar a versão vigente do plano.
7. Consultar contexto e análises datadas, corrigir registros e exportar a memória pessoal.

As áreas da interface agrupam o dia, energia, alimentação, corpo/check-in, objetivos, treino/sono, assistente, saúde/documentos e integrações/dados. A disponibilidade real de Garmin, Hevy e IA depende da configuração e do fornecedor; um conector configurado não comprova sucesso de uma sincronização.

## Organização dos componentes

| Componente | Responsabilidade |
| --- | --- |
| `dashboard/server.py` | Aplicação autenticada, proteção de sessões/CSRF e rotas legadas |
| `dashboard/personal_api.py` | Rotas pessoais, importações, análise, documentos, planejamento e exportação |
| `dashboard/snapshot.py` | Projeção de consulta da base esportiva legada e contexto de saúde disponível |
| `dashboard/imports.py` | CSV/GPX/FIT, recibos idempotentes, vínculos reversíveis e overlay sem reescrever datasets |
| `dashboard/health.py` | Perfil/objetivos versionados, gasto/balanço, progresso e propostas determinísticas |
| `dashboard/food_store.py` | Diário revisável, calorias pendentes, cobertura e histórico de alterações |
| `dashboard/nutrition.py` | Validação das estimativas alimentares e chamada opcional da IA |
| `dashboard/nutrition_targets.py` | Metas alimentares diárias com Ollama, contexto datado, limites e versões do plano |
| `dashboard/day_review.py` | Análise do dia com horário, refeições, treino e recuperação, com incertezas explícitas |
| `dashboard/assistant.py` | Contexto limitado ao período, análise/importação de resposta e proveniência |
| `dashboard/artifacts.py` | Documentos, observações revisadas, receitas/favoritos, planejamento e análises |
| `dashboard/provider_settings.py` | Configuração privada e credenciais cifradas, sem retorná-las nas respostas |
| `dashboard/repository.py` | Datasets PostgreSQL versionados e adaptador operacional PostgreSQL/SQLite |
| `dashboard/pipeline.py` / `dashboard/jobs.py` | Trabalhos, sincronização isolada, reconstrução e estados de execução |
| `dashboard/backup.py` | Arquivo privado cifrado e verificação de integridade por manifesto |

Os módulos de cálculo não chamam Garmin, Hevy ou IA. Importação/sincronização e geração de resposta são operações independentes. Falha do fornecedor não impede consulta, cadastro manual ou cálculo com dados já disponíveis.

## Persistência e histórico

Datasets esportivos mantêm sua camada legada de arquivos ou PostgreSQL, conforme configuração. O repositório PostgreSQL preserva revisões, bytes originais, projeções estruturadas e controle de concorrência. Nenhuma importação pessoal substitui esses datasets.

As operações pessoais usam `operational_db`: SQLite em instalações/testes locais e schema `operations` no PostgreSQL configurado. A migração `004_personal_health.sql` inclui estado/revisões pessoais, diário alimentar, artefatos e importações. Alterações relacionadas são transacionais; clientes podem informar a revisão esperada para impedir perda de edições concorrentes.

Perfil, preferências, objetivos, medidas, planos, propostas e decisões pertencem a conceitos diferentes. Perfil e objetivos têm vigência; uma alteração atual não deve mudar o contexto histórico silenciosamente. Planos são versões imutáveis: correção, aceite e retorno a uma referência anterior publicam uma nova versão.

Originais de atividades ficam em `runtime/personal-imports`; documentos em `runtime/personal-documents`; imagens alimentares no runtime privado. Identificadores de conteúdo geram os caminhos; nomes de cliente não autorizam acesso a arquivos locais. Os arquivos precisam acompanhar o banco em backup e migração.

## Alimentação e cobertura

Salvar uma refeição na interface grava a descrição e a foto antes da inferência. A IA calcula e registra os nutrientes automaticamente, sem etapa separada de análise ou confirmação. A origem fica identificada como estimativa da IA. Se a IA não estiver configurada ou falhar, a refeição continua salva com calorias pendentes. Editar e salvar recalcula a partir da descrição e reutiliza a foto registrada. A edição conserva o identificador da refeição, histórico e controle de revisão; repetir um salvamento já concluído com o mesmo token não cria outra refeição nem outra chamada. O modo anterior da API permanece disponível para compatibilidade com importação de registros estruturados.

Cobertura alimentar e cobertura numérica são independentes:

- Dia vazio: ingestão desconhecida.
- Dia parcial: subtotal registrado; faltam refeições ou confirmação de completude.
- Dia declarado completo: o usuário informa que incluiu tudo; porções ainda podem ser estimadas.
- Calorias pendentes: uma refeição ou item sem valor utilizável impede tratar o subtotal como ingestão diária total, mesmo quando o dia está declarado completo.
- Jejum declarado: pode representar zero ingestão; exige declaração explícita, distinta de falta de registro.

Uma exclusão ou alteração pode reabrir a conferência do dia. Favoritos/receitas e refeições durante treino convergem para o mesmo diário, sem um segundo total incompatível. Imagens não comprovam porções, preparo ou ingredientes invisíveis; a revisão continua necessária.

## Métodos de gasto e balanço

A preferência `energy_method` determina a escolha de gasto por dia:

- `auto` (padrão): total manual com cobertura completa; total completo da origem; modelo integral do perfil; fonte parcial/desconhecida quando o modelo estiver indisponível.
- `wearable`: usa somente o total diário da origem, preservando cobertura parcial/desconhecida e ausência. Não preenche as lacunas com o modelo.
- `model`: usa somente a referência declarada/calculada do perfil. Entradas insuficientes deixam o gasto indisponível.

As fontes são alternativas; um total manual não é parcela extra. Quando `auto` escolhe o modelo diante de um wearable parcial, o resultado identifica a origem `profile_model` ou `profile_declared`, `coverage_basis: modeled_full_day` e 24 horas modeladas. Horas observadas continuam ausentes no modelo. O wearable permanece nas alternativas com sua cobertura original, acompanhado da limitação explicada; seus valores não são completados nem somados ao modelo.

O gasto diário Garmin vem de `data/daily_energy.json`, com componentes separados, cobertura e método. O total inclui a atividade/exercício já contabilizados pela origem; os componentes nunca são somados novamente ao total. Ver [IMPORTS.md](IMPORTS.md) para semântica, contratos e preservação de respostas parciais.

`personal_energy_mifflin_v1` usa o modelo codificado Mifflin-St Jeor para adultos com entradas suficientes:

```text
repouso = 10 × peso_kg + 6,25 × altura_cm − 5 × idade + constante
constante = 5 ou −161 conforme o parâmetro exigido pelo modelo
gasto total estimado = repouso × fator de atividade declarado
```

A fórmula de repouso corresponde ao trabalho de [Mifflin et al. (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/). Essa referência fundamenta a equação de repouso; não valida o fator declarado de atividade, os limites de ingestão nem as heurísticas de adaptação desta aplicação.

O fator já representa a atividade habitual; calorias isoladas de treinos não são acrescentadas. Um total de perfil declarado pode substituir o modelo. Entradas insuficientes deixam o gasto indisponível. A implementação não escolhe uma constante binária para um perfil incompatível ou sem esse parâmetro. O resultado é uma estimativa, com fonte/método e hipóteses explícitos.

```text
balanço estimado = ingestão − gasto total
déficit estimado = gasto total − ingestão
margem para a meta = meta de ingestão − total registrado
```

A margem não comprova déficit. Déficit retrospectivo só existe quando o diário é utilizável, o gasto cobre o dia e não é projeção. Modelo para hoje/futuro aparece como projetado; cobertura de horas inferior ao dia permanece parcial. O período mostra quantidade de dias utilizáveis, soma e média nesses dias, sem preencher lacunas com zero ou extrapolar a semana silenciosamente.

## Objetivos, plano inicial e adaptação

Objetivos têm tipo, descrição, prioridade, estado, vigência e indicadores. O objetivo principal ativo orienta a revisão; pausados/concluídos/arquivados permanecem históricos. Diferentes tipos podem coexistir, com limitações explícitas quando há conflito.

Um plano inicial pode usar uma meta declarada ou uma referência calculada com perfil suficiente. Objetivos sem base numérica continuam com plano provisório de acompanhamento. Objetivos esportivos ou comportamentais não exigem déficit; o motor atual só adapta numericamente a ingestão para tipos corporais compatíveis.

Para ganho de peso, informar meta de ingestão e ritmo desejado é condição para adaptação numérica. O sistema não presume uma taxa de ganho nem usa uma meta de manutenção como se já fosse uma proposta de ganho.

A política atual é `conservative_trend_v1`. Os parâmetros estão expostos no resumo e nas preferências; não são ocultados como conclusões da IA. Padrões iniciais do software:

| Parâmetro | Padrão |
| --- | --- |
| Janela de revisão | 14 dias |
| Frequência sugerida | 7 dias |
| Cobertura alimentar mínima | 10 dias completos e calorias utilizáveis |
| Medidas mínimas | 4 datas distintas, abrangendo pelo menos 7 dias |
| Tamanho da proposta energética | 100 kcal |
| Déficit inicial sugerido para objetivo compatível | 250 kcal, limitado pela política |
| Tolerância de tendência | 0,15 kg/semana |
| Tolerância de adesão alimentar | 15% da meta |
| Limite percentual de déficit planejado | 15% da referência de gasto |
| Piso configurável de meta | 1.200 kcal, também limitado pela referência de repouso disponível |

Estes valores são parâmetros revisáveis de uma política inicial. Não demonstram adequação clínica para qualquer pessoa nem garantem resultado. O código inclui limites adicionais de alvo e de alteração, cuja avaliação especializada permanece uma tarefa de validação do método.

O progresso corporal usa regressão linear de peso por dia, expressa por semana, e conserva os pontos reais. Não atribui automaticamente a mudança de peso a gordura ou converte kcal em quilos garantidos.

A revisão compara cobertura, tendência, ingestão em relação ao plano, recuperação relatada, sono, carga e objetivos concorrentes. Pode manter, propor ajuste ou pedir dados melhores. Há condições que bloqueiam uma redução adicional; não há compensação punitiva por uma refeição nem ajuste baseado em um único dia.

A opção de metas alimentares automáticas publica diariamente calorias e proteína com Ollama, usando peso, objetivo, atividades e recuperação. Também recalcula após mudanças relevantes. A alimentação mostra registrado/meta e saldo provisório quando há nutrientes pendentes. A opção pode ser pausada; versões anteriores e planos futuros são preservados. Veja [NUTRITION_TARGETS.md](NUTRITION_TARGETS.md) para os dados exigidos, os parâmetros, o histórico e o tratamento de falhas.

O fluxo separado de propostas continua exigindo decisão do usuário. A proposta guarda evidências, método, versão anterior, sugestão, motivo e próxima revisão. Seu fingerprint é revalidado no aceite; alterações relevantes invalidam a proposta. Uma decisão tardia tem vigência posterior à data real de aceite, sem reescrever metas passadas. Pause as metas automáticas para manter uma referência manual ou profissional sem substituição pela IA.

## IA e escopo autorizado

Hoje e Alimentação oferecem **Analisar meu dia**: monta o prompt com horário local, meta, cobertura alimentar/energética, treino, recuperação, planejamento e relato opcional. Salva a resposta no histórico do assistente sem alterar metas ou registros. A diferença para a meta não é apresentada como déficit comprovado. O contexto e o prompt continuam consultáveis; falhas preservam respostas anteriores. Método e limites: [DAY_REVIEW.md](DAY_REVIEW.md).

A estimativa alimentar envia o conteúdo da refeição e eventual imagem selecionada. O assistente prepara contexto do período selecionado: perfil, objetivos, planos, alimentação, energia, atividades, sono, corpo e check-ins. Documentos/exames só entram mediante opção explícita; geometria GPX não é anexada por causa de uma refeição ou pergunta geral.

As respostas preservam pergunta/contexto, período, modelo/origem, fingerprint e data. Uma resposta importada é identificada como importada. Reutilização por fingerprint e limite diário reduzem chamadas repetidas. O limite usa a data atual no fuso do perfil, mesmo quando a pergunta é sobre um período histórico; resposta em cache e resposta importada não criam uma nova chamada ao fornecedor. O processo serializa cache, quota e publicação do assistente para o deployment atual com um worker. Texto de documentos ou fontes é tratado como dado, sem autorização para alterar planos, credenciais ou sistemas externos.

O opt-in de dados médicos e o pedido de extração por IA exigem valores booleanos explícitos. Texto como `"false"` é rejeitado, sem chamada à IA. Uma imagem cujo original esteja ausente permanece registrada, mas sua extração é bloqueada com indicação para restaurar ou reenviar o arquivo.

A IA pode explicar e propor; somas, balanços, progresso e publicação de plano continuam operações determinísticas. A opção manual/importada mantém o uso quando a IA estiver indisponível. Chamadas reais e o conteúdo das respostas dependem do fornecedor e não são comprovados por testes com mocks.

## Portabilidade, privacidade e operação

`GET /api/export` fornece JSON estruturado de datasets, dados pessoais e suas revisões, diário, importações, decisões, artefatos e contexto, sem incluir credenciais. Documentos têm metadados e endpoint autenticado de download.

`GET /api/export/archive` entrega ZIP com `context.json` e `manifest.json`. Por padrão não inclui anexos; os parâmetros booleanos `include_documents`, `include_food_images` e `include_imports` selecionam documentos pessoais/legados, imagens alimentares e originais das importações, respectivamente. O manifesto identifica a seleção e os hashes/tamanhos dos anexos incluídos. Credenciais, sessões e chaves de recuperação ficam excluídas. O ZIP temporário é removido após o envio. A leitura desse pacote por uma implementação independente continua sendo uma validação específica de portabilidade.

Desconectar uma fonte interrompe novas coletas e preserva o histórico. Exclusão de um item ativo pode conservar revisões privadas e backups anteriores; a interface deve informar essa retenção. Credenciais de fornecedores ficam cifradas e seu status não devolve segredos.

Backups usam cifragem autenticada e manifesto com hashes. O backup novo após a atualização teve 1.399 arquivos conferidos por integridade e passou por `restore-test`: o comando criou um banco PostgreSQL temporário, restaurou o dump, comparou a revisão ativa e todos os bytes dos datasets e removeu somente esse banco gerado. O resultado foi `verified: true`, `postgres_restore: true`, `byte_exact: true`. O backup anterior, com 1.387 arquivos, também havia passado pelo mesmo ensaio. Esses resultados comprovam as restaurações PostgreSQL exercitadas; ainda falta iniciar todo o sistema com runtime e anexos restaurados em uma instalação nova.

## Validações e limites atuais

O mapa de requisitos, cenários e evidências está em [ACCEPTANCE.md](ACCEPTANCE.md). O contrato de arquivos e energia está em [IMPORTS.md](IMPORTS.md).

Na rodada final, passaram 133 testes Python com PostgreSQL descartável (105 de dashboard e 28 da raiz), sem testes ignorados, além de três testes Node e builds Docker de API/web. A instalação PostgreSQL vazia foi inicializada e autenticada sem introduzir fatos de uma base anterior. Dois relatórios foram gerados com Typst real, incluindo o cenário de primeira instalação vazia.

A produção foi atualizada com API/web em `http://localhost:8787`; dez endpoints autenticados responderam 200 e os dados anteriores foram preservados. A inspeção móvel de Hoje, alimentação, perfil, objetivos e assistente em 390 px não encontrou overflow horizontal. Ver [ACCEPTANCE.md](ACCEPTANCE.md) para limites de cada execução.

A IA remota permaneceu sem chave configurada; nenhuma chamada real foi validada. As conexões e respostas reais de Garmin, Hevy e demais fornecedores remotos continuam sem verificação nesta entrega. Os modos manual/importado e os cálculos sobre dados disponíveis mantêm seu funcionamento independente dessas chamadas.

Pontos que requerem validação operacional adicional: autenticação e cobertura reais dos fornecedores; inicialização integral após restauração em outro ambiente; toda a jornada móvel com teclado, decisões, vínculos e falhas; disponibilidade e custo de IA; leitura independente do pacote portátil; e avaliação dos parâmetros do motor adaptativo. Variações TCX, exportações CSV de cada fornecedor, hardware direto e outras plataformas continuam adaptadores posteriores. Sessões pessoais importadas não entram silenciosamente no modelo legado de carga.
