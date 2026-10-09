# AscentIQ — saúde e fitness pessoal

Frontend: **Next.js 16.4 · React 19.3 · Tailwind 4.3 · shadcn/ui**, com rotas App Router e componentes em TypeScript estrito. Sem styled-components.

Uma plataforma individual para reunir treinos, alimentação, sono, medidas e objetivos. Os registros ficam estruturados e datados; os cálculos mostram a origem e a cobertura dos dados. A inteligência artificial ajuda a interpretar esse histórico e estimar refeições, sempre com revisão do usuário.

## O que funciona

- Dashboard com calorias e proteína registradas em relação às metas, treinos, carga, sono, objetivo principal e situação do check-in. A interpretação da cobertura fica no ícone de informação; um diário vazio nunca prova jejum.
- Garmin Connect e Hevy, sincronização incremental, sono preservado e consolidação de sessões de força. Importação manual e por CSV, FIT e GPX, com originais privados, repetição segura e reconciliação reversível.
- Nutrition com refeições em grid paginado e cadastro/edição em modal por texto ou foto. Salvar solicita a estimativa da IA automaticamente; falhas preservam a refeição como pendente para nova tentativa. Receitas por porções e cobertura do dia continuam disponíveis.
- Perfil, preferências, medidas, check-ins e objetivos com prioridades. Metas alimentares diárias com IA local, planos datados e propostas de adaptação com evidência, revisão e aceite explícito.
- Consumo/meta de calorias e nutrientes na alimentação, com saldo restante. Peso, objetivo e treinos orientam a atualização automática, que pode ser pausada.
- Análise do dia em modal, aberta por botão no Dashboard ou em Nutrition: considera horário, registros, recuperação e relato pessoal, com resposta salva e prompt consultável. Check-in e objetivos também abrem em modais.
- Assistente flutuante, não bloqueante, com conversa e rascunho preservados ao minimizar, fechar o painel ou navegar. Contextos de dia, mês, objetivos e período definido consultam registros atualizados; perguntas seguintes usam trechos de até três respostas recentes da mesma conversa.
- Workouts com Visão geral, Corrida e Força; análise de treinamento em modal na Visão geral. Sleep tem área própria, filtros, gráficos e histórico paginado.
- Documentos privados com extração e revisão. Planejamento, relatórios e painéis de histórico/decisões saíram da navegação; dados, versões e serviços existentes continuam preservados.
- PostgreSQL, autenticação local, credenciais de fontes criptografadas, exportação JSON/ZIP e backup criptografado com teste de restauração separado.

## Navegação e uso

O menu flutuante à esquerda contém **Dashboard, Workouts, Nutrition e Sleep**.
Em telas pequenas, o botão abre um menu compacto. A conta fica à direita da topbar,
com **Conta e perfil**, **Dados e fontes** e **Sair** em um dropdown.
A sincronização Garmin/Hevy e a configuração da IA ficam em Dados e fontes;
documentos privados são acessados a partir dessa área.

No Dashboard, escolha o dia e use **Analisar meu dia**, **Registrar/editar check-in**,
**Objetivos** ou **Assistente**. O ícone de informação abre **Como ler este dia**.
Em Nutrition, **Adicionar refeição** abre o formulário; **Editar** abre os dados
da refeição no mesmo modal. Operações de gravação impedem envio duplicado e
fechamento durante a operação; rascunhos alterados exigem confirmação para descarte.

Listas, tabelas e grids usam **10 registros por página**, com opção de **15**.
Os filtros operam sobre o conjunto pertinente, enquanto totais, médias e gráficos
usam todo o período. A paginação da conversa é consultada no servidor; os demais
painéis paginam os registros carregados do snapshot ou da consulta da área.

O assistente abre no canto inferior esquerdo sem bloquear o site. Selecione o
contexto antes de perguntar: **Dia**, **Mês**, **Objetivos**, **Últimos dias** ou
**Período definido**. Mês usa o calendário real, até a data atual quando for o mês
em andamento. Períodos personalizados aceitam de 1 a 90 dias. A tela informa o
intervalo, quantos detalhes foram incluídos e eventuais resumos para caber no modelo.
Totais do período permanecem representados; nem todas as refeições, atividades ou
séries individuais entram em cada pergunta. Referências médicas e documentos só
entram mediante seleção explícita. Respostas anteriores com contexto médico são
omitidas da continuidade quando essa seleção estiver desativada. O assistente
explica e sugere; as respostas não alteram automaticamente seus registros ou plano.

## Começar do zero

Docker Desktop deve estar em execução. Copie `.env.example` para `.env`, preencha duas senhas distintas de banco e mantenha `DATABASE_BACKEND=postgres`. Credenciais Garmin, Hevy e IA são opcionais e podem ser cadastradas no painel.

```powershell
docker compose build api frontend web
docker compose --profile local-ai up -d db ollama
docker compose --profile local-ai exec ollama ollama pull qwen3.5:4b
docker compose --profile maintenance run --rm db-tools bootstrap
docker compose --profile maintenance run --rm db-tools init-empty
docker compose up -d api frontend web
```

Abra [AscentIQ local](http://localhost:8787). O primeiro acesso está no arquivo privado `runtime/dashboard/access.txt`, salvo quando não foi configurada uma senha no ambiente. Defina seu perfil e objetivo, conecte fontes ou registre dados manualmente. Exemplos deste repositório não viram registros pessoais.

Para migrar uma base anterior, siga [DATABASE.md](docs/DATABASE.md): use a importação revisada no lugar de `init-empty`. Não reimporte arquivos antigos sobre uma revisão mais recente do PostgreSQL.

## Especificação e validação

- [SPEC completa de produto](SPEC_PLATAFORMA_SAUDE_FITNESS.md)
- [Interface simplificada e critérios de aceite](docs/SPEC_SIMPLIFICACAO_PLATAFORMA.md)
- [Uso, instalação e operação](dashboard/README.md)
- [Funcionalidades e política de adaptação](docs/PLATFORM.md)
- [Contratos de importação](docs/IMPORTS.md)
- [Requisitos e evidência de aceite](docs/ACCEPTANCE.md)
- [Armazenamento e recuperação](docs/DATABASE.md)
- [IA local sem cobrança de API, com Ollama](docs/OLLAMA.md)
- [Metas alimentares automáticas e parâmetros](docs/NUTRITION_TARGETS.md)
- [Análise do dia com alimentação, treino e horário](docs/DAY_REVIEW.md)

```powershell
docker compose --profile maintenance run --rm db-tools test
```

Esse comando cria um banco temporário, verifica a instalação vazia e executa as suítes de API, dados, energia, adaptação, importação, concorrência e recuperação. O GitHub Actions executa os testes com PostgreSQL descartável e constrói a UI.

No ambiente local, com `.venv` instalado a partir de `dashboard/requirements-dev.txt`, os mesmos testes e verificações do CI são:

```powershell
python -B -m dashboard.tests.empty_installation_smoke
pytest
ruff check .
ruff format --check .
mypy
python -m dashboard.openapi_export --check
```

O commit de formatação está em `.git-blame-ignore-revs`; configure uma vez com `git config blame.ignoreRevsFile .git-blame-ignore-revs` para o `git blame` ignorá-lo.

## Desenvolvimento da interface

O frontend oficial fica em `dashboard/web`. Node 24 LTS é necessário:

```powershell
cd dashboard/web
npm ci
npm run lint
npm run typecheck
npm run check:styles
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Os tipos de `src/lib/api/generated/openapi.d.ts` são derivados de `dashboard/openapi.json`; ao alterar endpoints ou envelopes no backend, regenere com `python -m dashboard.openapi_export` na raiz e `npm run contracts` em `dashboard/web` (`npm run contracts:check` verifica se estão atualizados).

Para desenvolvimento com o backend na mesma origem, configure `DEV_API_URL` com a URL interna da API e execute `npm run dev`. Em produção, `frontend` executa Next standalone como usuário sem privilégios e `web` é o gateway Nginx; somente o gateway publica a porta 8787. As consultas de saúde não são armazenadas em cache compartilhado. Os testes E2E usam um backend sintético isolado, sem escrever no diário real.

Instruções de manutenção estão em [AGENTS.md](dashboard/web/AGENTS.md). O [plano e resultado da migração](docs/PLANO_MIGRACAO_NEXT_SHADCN.md) registra versões, validação, skills e rollback. Para instalar a PWA pelo IP da rede local, o navegador ainda exige HTTPS confiável; localhost permite a validação local do service worker.

## Limites explícitos

O cálculo de gasto e a adaptação são estimativas e regras transparentes do produto. Salvar uma refeição autoriza a estimativa automática da IA. A opção de metas diárias publica planos com limites e histórico; pode ser pausada. O fluxo de propostas continua exigindo aceite. Ollama executa o modelo local sem cobrança por chamada; precisa do modelo baixado e de recursos do computador. OpenAI é opcional e exige chave/créditos da API. Não há fallback automático para API paga no modo local. Integrações dependem do serviço de origem e das credenciais do usuário. Novos conectores móveis, voz e códigos de barras permanecem evoluções opcionais da SPEC.

Dados reais, documentos, fotos, relatórios e credenciais não fazem parte do código público. O servidor web escuta somente no endereço local por padrão.
