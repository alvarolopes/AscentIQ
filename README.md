# AscentIQ — saúde e fitness pessoal

Uma plataforma individual para reunir treinos, alimentação, sono, medidas e objetivos. Os registros ficam estruturados e datados; os cálculos mostram a origem e a cobertura dos dados. A inteligência artificial ajuda a interpretar esse histórico e estimar refeições, sempre com revisão do usuário.

## O que funciona

- Painel do dia com alimentação registrada, gasto estimado, déficit utilizável, margem para a meta e limites de cobertura. Um diário vazio nunca prova jejum.
- Garmin Connect e Hevy, sincronização incremental, sono preservado e consolidação de sessões de força. Importação manual e por CSV, FIT e GPX, com originais privados, repetição segura e reconciliação reversível.
- Diário alimentar por texto ou foto, estimativa automática da IA ao salvar, refeições pendentes em caso de falha, correções, favoritos e receitas por porções. Cobertura do dia e estimativas pendentes são informações independentes.
- Perfil, preferências, medidas, check-ins e objetivos com prioridades. Metas alimentares diárias com IA local, planos datados e propostas de adaptação com evidência, revisão e aceite explícito.
- Consumo/meta de calorias e nutrientes na alimentação, com saldo restante. Peso, objetivo e treinos orientam a atualização automática, que pode ser pausada.
- Assistente com período e contexto visíveis, histórico de respostas e uso manual de outra IA. Referências médicas só entram mediante seleção explícita.
- Documentos privados com extração e revisão, planejamento de refeições e treinos, gráficos e relatórios esportivos em HTML/PDF.
- PostgreSQL, autenticação local, credenciais de fontes criptografadas, exportação JSON/ZIP e backup criptografado com teste de restauração separado.

## Começar do zero

Docker Desktop deve estar em execução. Copie `.env.example` para `.env`, preencha duas senhas distintas de banco e mantenha `DATABASE_BACKEND=postgres`. Credenciais Garmin, Hevy e IA são opcionais e podem ser cadastradas no painel.

```powershell
docker compose build api web
docker compose --profile local-ai up -d db ollama
docker compose --profile local-ai exec ollama ollama pull qwen3.5:4b
docker compose --profile maintenance run --rm db-tools bootstrap
docker compose --profile maintenance run --rm db-tools init-empty
docker compose up -d api web
```

Abra [AscentIQ local](http://localhost:8787). O primeiro acesso está no arquivo privado `runtime/dashboard/access.txt`, salvo quando não foi configurada uma senha no ambiente. Defina seu perfil e objetivo, conecte fontes ou registre dados manualmente. Exemplos deste repositório não viram registros pessoais.

Para migrar uma base anterior, siga [DATABASE.md](docs/DATABASE.md): use a importação revisada no lugar de `init-empty`. Não reimporte arquivos antigos sobre uma revisão mais recente do PostgreSQL.

## Especificação e validação

- [SPEC completa de produto](SPEC_PLATAFORMA_SAUDE_FITNESS.md)
- [Uso, instalação e operação](dashboard/README.md)
- [Funcionalidades e política de adaptação](docs/PLATFORM.md)
- [Contratos de importação](docs/IMPORTS.md)
- [Requisitos e evidência de aceite](docs/ACCEPTANCE.md)
- [Armazenamento e recuperação](docs/DATABASE.md)
- [IA local sem cobrança de API, com Ollama](docs/OLLAMA.md)
- [Metas alimentares automáticas e parâmetros](docs/NUTRITION_TARGETS.md)

```powershell
docker compose --profile maintenance run --rm db-tools test
```

Esse comando cria um banco temporário, verifica a instalação vazia e executa as suítes de API, dados, energia, adaptação, importação, concorrência e recuperação. O GitHub Actions executa os testes com PostgreSQL descartável e constrói a UI.

## Limites explícitos

O cálculo de gasto e a adaptação são estimativas e regras transparentes do produto. Salvar uma refeição autoriza a estimativa automática da IA. A opção de metas diárias publica planos com limites e histórico; pode ser pausada. O fluxo de propostas continua exigindo aceite. Ollama executa o modelo local sem cobrança por chamada; precisa do modelo baixado e de recursos do computador. OpenAI é opcional e exige chave/créditos da API. Não há fallback automático para API paga no modo local. Integrações dependem do serviço de origem e das credenciais do usuário. Novos conectores móveis, voz e códigos de barras permanecem evoluções opcionais da SPEC.

Dados reais, documentos, fotos, relatórios e credenciais não fazem parte do código público. O servidor web escuta somente no endereço local por padrão.
