# AscentIQ — operação da plataforma pessoal

A interface reúne Hoje, Alimentação, Treino, Saúde, Objetivos, Assistente e Dados e fontes. Os dados ficam no ambiente individual, com fontes, datas e revisões. O PDF continua limitado ao contexto esportivo.

## Instalação vazia

Copie `.env.example` para `.env`. Configure senhas diferentes em `PGPASSWORD` e `POSTGRES_ADMIN_PASSWORD`; mantenha `DATABASE_BACKEND=postgres`. Não publique esse arquivo. Docker Desktop deve estar em execução.

```powershell
docker compose build api web
docker compose up -d db
docker compose --profile maintenance run --rm db-tools bootstrap
docker compose --profile maintenance run --rm db-tools init-empty
docker compose up -d api web
docker compose ps
```

`init-empty` cria uma revisão sem dados apenas se não existir revisão ativa. Não importa os exemplos públicos nem substitui uma base existente. Abra http://localhost:8787. Quando nenhuma senha de painel foi configurada, o acesso está em `runtime/dashboard/access.txt`. O login é independente das credenciais Garmin, Hevy e IA.

Para migrar dados anteriores, use o fluxo de importação e validação de [DATABASE.md](../docs/DATABASE.md) no lugar de `init-empty`. Em uma instalação existente, faça backup, construa as imagens, execute `bootstrap` para aplicar as migrações novas e recrie API/web. Nunca reimporte JSON antigo sobre o PostgreSQL atual.

## Uso cotidiano

- **Hoje:** registros alimentares, gasto e origem, margem para a meta, déficit estimado, cobertura, contexto de recuperação e check-in.
- **Alimentação:** texto ou foto, análise com IA sob demanda, revisão dos alimentos e valores, entrada manual e registro pendente. Edite, copie ou restaure versões anteriores. Declare o dia completo quando todos os alimentos estiverem registrados; calorias pendentes continuam desconhecidas. Receitas guardam rendimento e permitem selecionar as porções consumidas.
- **Treino:** histórico por modalidade, força consolidada, gráficos de carga, sono no contexto diário, planejamento e relatórios. GPX de percurso é uma rota, não prova de treino realizado.
- **Saúde:** perfil, preferências, medidas, check-ins, sono, referências corporais e exames antigos com suas datas. Envie documentos PDF/texto/imagem, confira a extração e revise os indicadores. IA documental só é acionada por seleção explícita.
- **Objetivos:** prioridades, critérios e prazo desejado. O plano inicial usa apenas referências suficientes; sem elas permanece provisório. Revisões produzem propostas com evidências e limitações. Aceitar cria uma versão com nova vigência; rejeitar preserva o plano. Mudança na evidência impede aceitar uma proposta desatualizada.
- **Assistente:** escolha período e escopo, confira contexto, faça perguntas ou importe respostas de outra IA. Referências médicas são opcionais. Respostas não alteram metas, refeições ou plano automaticamente.
- **Dados e fontes:** conexão Garmin/Hevy/IA, status e última coleta, importação CSV/FIT/GPX, registro manual, reconciliação e exportação JSON/ZIP com anexos selecionados.

Falta de registro não significa zero. Um diário parcial ou com calorias desconhecidas não confirma déficit. O gasto total do relógio já inclui as atividades: exercício não é somado novamente. O modo automático prioriza totais completos e pode usar um modelo integral identificado quando há perfil suficiente, preservando a fonte parcial como alternativa. O modo estrito de wearable e a escolha explícita de modelo ficam nas preferências. Hoje pode permanecer projeção.

A equação e as regras de adaptação estão em [PLATFORM.md](../docs/PLATFORM.md). Os limiares são políticas transparentes do produto, não garantias clínicas. Os contratos e exemplos sintéticos de arquivos estão em [IMPORTS.md](../docs/IMPORTS.md).

## Fontes e IA

Ollama local está disponível sem cobrança de API. Veja [OLLAMA.md](../docs/OLLAMA.md) para instalar o modelo em Docker, habilitar NVIDIA e selecionar o provedor em Dados e fontes. Quando Ollama é selecionado, alimentação, assistente e extração com IA usam somente o modelo local; falhas não acionam OpenAI. As estimativas alimentares continuam exigindo revisão e salvamento.

Credenciais podem ser configuradas em Dados e fontes. Elas ficam criptografadas em `runtime/dashboard/connections`; a chave local deve permanecer privada e entrar no backup. A API devolve status, sem devolver segredos. Desconectar interrompe o uso da fonte e preserva seu histórico. Variáveis privadas de ambiente continuam suportadas.

Garmin revisita uma janela sobreposta para correções de atividades e sono. Hevy usa importação incremental e mantém exercícios/séries quando fornecidos. Falhas preservam observações anteriores e aparecem no histórico de execução. Uma fonte sem credenciais não impede atualizar a outra disponível. MFA Garmin pode exigir autenticação externa antes da sincronização.

Quando OpenAI é selecionado, a IA depende de `OPENAI_API_KEY` e acesso ao modelo em `OPENAI_MODEL`; essas chamadas são cobradas pelo provedor. A chave permanece no servidor e as chamadas usam `store: false`, timeout e erros sem segredos. Ollama local não exige chave nem créditos de API. O texto/foto alimentar não recebe o histórico médico. A pergunta ao assistente recebe somente o período e escopo escolhidos. Registro manual e importação de respostas funcionam sem chave.

O cache evita repetir análises idênticas. O assistente serializa geração e limita chamadas por dia no fuso pessoal; isso não é uma cota global para todos os recursos de IA. Não há geração automática de resposta a cada registro.

## Persistência, agenda e relatórios

PostgreSQL mantém datasets originais e projeções, registros pessoais, diário alimentar, importações, artefatos, jobs e sessões. Medidas, metas, planos, decisões e alimentação conservam revisões. O diário antigo em `runtime/dashboard/food-diary` é lido sem remover os originais. SQLite é uma alternativa de testes/recuperação, não o backend padrão do Compose.

Garmin e sono são coletados diariamente às 10h America/Sao_Paulo, com até três tentativas espaçadas por uma hora. O relatório semanal é produzido na segunda às 07h, quando o ambiente está ligado. Preferências do usuário controlam a agenda; estado e tentativas sobrevivem ao reinício. Requer computador/Docker em execução e relógio sincronizado com a plataforma.

`Gerar com a base atual` não contata provedores. O relatório é publicado somente depois de validar HTML e PDF; falha preserva o anterior. A instalação sem atividades mantém carga desconhecida. O modelo de carga existente conserva constantes de 42/7 dias; sessões somente Hevy podem aparecer no diário sem contribuição à curva cardiovascular. As curvas são estimativas locais, não TSS oficial ou percentual de condicionamento.

## Privacidade e recuperação

O web escuta em `127.0.0.1:8787`; API e banco não têm portas públicas. Rotas de dados exigem sessão, cookies são HttpOnly/SameSite, mutações verificam origem e login tem limite de tentativas. O service worker não armazena respostas de saúde. A interface é responsiva; acesso físico pelo celular exige uma implantação privada HTTPS apropriada.

Documentos e fotos ficam em armazenamento privado; downloads validam uma lista de arquivos permitidos. Remover um registro o retira da visão ativa, mas revisões privadas e backups mantêm a história. Exportações de contexto e ZIP não incluem credenciais, sessões ou chaves de recuperação.

```powershell
docker compose exec -T api python -m dashboard.backup --database
docker compose --profile maintenance run --rm db-tools restore-test --archive /app/runtime/backups/ARCHIVE.tar.gz.enc --output /app/runtime/backups
```

Backups usam AES-256-GCM e verificação SHA-256 de cada arquivo. O teste restaura o dump em banco temporário separado e compara os datasets. A chave `runtime/backups/recovery.key` é necessária para recuperar e não está no arquivo criptografado. Guarde cópias seguras do backup e da chave fora do disco local; nenhum destino externo é configurado automaticamente. Veja [DATABASE.md](../docs/DATABASE.md) para restauração e rollback.

## Validação e manutenção

```powershell
docker compose --profile maintenance run --rm db-tools test
docker compose logs --tail 80 api web
docker compose stop api web
```

Os testes usam banco descartável e dados sintéticos, incluindo instalação vazia, concorrência, importações repetidas, déficit sem duplicar atividade, cobertura e adaptação efetiva. [ACCEPTANCE.md](../docs/ACCEPTANCE.md) registra o que foi executado e o que ainda exige prova operacional. Mantenha um único worker API para o agendamento e a serialização individual. Nunca publique logs crus de conectores, dados pessoais, `.env`, runtime, fotos ou relatórios privados. Pare somente os serviços desta aplicação; nunca remova os volumes para atualizar.
