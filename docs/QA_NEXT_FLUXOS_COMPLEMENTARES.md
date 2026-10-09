# QA complementar da migração Next.js

Data: 08/10/2026. Frontend canônico: `dashboard/web`.

Os cenários abaixo foram executados no Chrome headless contra um servidor HTTP local com fixtures inventadas. Os componentes reais, o cliente de API, o QueryProvider, os componentes shadcn e o CSS compilado foram usados. Todas as mutações chegaram somente ao servidor sintético; nenhum cadastro, documento, credencial ou exportação real foi lido ou alterado.

## Resultado

| Área           | Cenários exercitados                                                | Evidência verificada                                                                                                                                                                                       |
| -------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Importação     | CSV, GPX e FIT; arquivo maior que 12 MB; clique duplo               | CSV/GPX enviados como texto; bytes FIT enviados em base64; `format` e `filename` corretos; arquivo grande rejeitado antes do POST; uma requisição por envio; arquivo e estado dirty limpos após sucesso    |
| Reconciliação  | Vincular, manter separadas e desfazer vínculo na segunda página     | `record_id`, `other_id` e `action` correspondem ao registro escolhido, sem confundir índices da página com índices da coleção; histórico de importações respeita 10/15 itens                               |
| Integrações    | Atualizar Garmin/Hevy e desconectar coleta                          | Uma chamada de job `sync` mesmo com clique duplo; endpoint de desconexão correto                                                                                                                           |
| Exportação     | Downloads JSON e ZIP com os três tipos de anexo selecionados        | Download iniciado pelo navegador, nomes e bytes sintéticos esperados; `include_documents`, `include_food_images` e `include_imports` enviados como `true`                                                  |
| Documentos     | Upload, abertura do original, revisão manual e remoção              | Conteúdo base64 preservado; identificação normalizada e data mantida; clique duplo não duplica upload; original aberto em outra janela; observações incorporadas apenas após confirmar revisão             |
| Documentos     | Remover com revisão aberta; cancelar e confirmar; limite de tamanho | Cancelar preserva documento e revisão sem POST; confirmar remove o documento e limpa a revisão/dirty; arquivo maior que 12 MB rejeitado sem POST                                                           |
| Medidas        | Criar, editar e remover; cancelar remoção                           | Valores numéricos corretos, ID preservado na edição e ID/revision atuais na remoção; cancelar não envia mutação                                                                                            |
| Medidas        | Conflito HTTP 409 e nova tentativa                                  | Consulta atualiza revision; peso e notas digitados permanecem no formulário; nova tentativa salva com revision atualizada                                                                                  |
| Assistente     | Mês, objetivos, últimos 30 dias e período definido                  | `period`, `days`, `start` e `end` correspondem ao contexto escolhido; dados médicos omitidos por padrão                                                                                                    |
| Assistente     | Conflito HTTP 409, atualização de contexto e nova tentativa         | Pergunta preservada; aviso permanece após atualização automática; nova tentativa usa fingerprint atualizado e referências das três respostas recentes                                                      |
| Assistente     | Mudança de escopo e falha na atualização do contexto após 409       | Mudança de escopo limpa o aviso sem apagar a pergunta; erro de consulta e aviso 409 aparecem juntos; refresh manual recupera contexto sem apagar o conflito; retry limpa o aviso e usa o fingerprint atual |
| Assistente     | Importar resposta externa; clique duplo                             | `manual_response` e fingerprint do contexto revisado preservados; uma mutação por envio; resposta aparece no histórico da conversa                                                                         |
| Contrato comum | Todas as mutações dos componentes                                   | Header `X-AscentIQ-Request: 1` presente; nenhuma exceção não tratada no navegador                                                                                                                          |

O QA anterior da migração também cobriu paginação 10/15 de fontes, documentos e resultados, validação de indicador em outra página, edição/remoção pelo índice original, consentimento explícito de extração e de contexto médico, continuidade/histórico de conversas, idempotência de atividade manual após falha, notas de medidas, referência energética datada, PWA e ausência de overflow das quatro telas em 390 px. Esta rodada fechou as lacunas sem repetir a revisão das fontes.

## Reproduzir

As regressões versionadas usam somente dados sintéticos. Na pasta `dashboard/web`:

```powershell
npm.cmd test
npm.cmd run test:e2e
npm.cmd run test:e2e -- tests/e2e/assistant-conflict.spec.ts
```

O harness complementar usado nesta sessão está fora do repositório em `../tmp/qa-next-owned-gaps.cjs`, relativo à raiz do projeto. Ele monta os componentes em memória, compila o CSS com PostCSS/Tailwind, abre Chrome via Playwright e cria sua própria API em `127.0.0.1` com porta livre. Não aponta para a instância real da plataforma.

Para repeti-lo neste ambiente, a partir da raiz do projeto:

```powershell
node ..\tmp\qa-next-owned-gaps.cjs
$env:QA_ONLY_ASSISTANT = '1'
node ..\tmp\qa-next-owned-gaps.cjs
Remove-Item Env:\QA_ONLY_ASSISTANT
```

O modo `QA_ONLY_ASSISTANT` repete apenas o trecho do assistente. O harness local depende dos caminhos de instalação de Chrome, Playwright e esbuild desta sessão; não é parte da suíte de CI e seu código bruto não foi adicionado ao repositório. Para recriar a validação em outro ambiente, use os seguintes contratos de fixtures:

1. `GET /api/integrations`: fonte fictícia configurada, 12 correspondências ambíguas, 12 vínculos, 21 importações e registros com IDs distintos. `POST /api/import/reconcile` modifica apenas as listas em memória. Faça as três ações na página 2 e confira os IDs dos payloads.
2. `POST /api/import`: devolve recibo e aviso inventados. Envie CSV/GPX de texto, FIT de seis bytes e arquivo de 12 MB mais um byte. Conte as requisições e compare os bytes originais com o payload.
3. `GET /api/export` e `/api/export/archive`: devolvem attachments sintéticos JSON/ZIP. Capture o evento de download e confira os parâmetros de anexos, sem baixar dados da API real.
4. `GET/POST /api/documents`: arquivo TXT inventado e armazenamento em memória. Os endpoints `/file`, `/review` e `/remove` devolvem somente esse conteúdo. Cancele a primeira confirmação de remoção e aceite a segunda.
5. `GET /api/personal`: perfil fictício, revision 7 e uma medida. No primeiro POST de nova medida devolva 409 e avance a revision para 8. Confirme preservação do rascunho e retry, depois edite e remova a medida criada.
6. `GET /api/assistant/context`: prompt inventado e fingerprint controlado; `/history`: respostas em memória. No POST escolhido devolva 409, avance o fingerprint e confira aviso, pergunta e retry. Uma resposta importada deve guardar o fingerprint revisado e omitir dados médicos sem consentimento.

## Correção encontrada durante o QA

O assistente apagava o aviso 409 ao iniciar a atualização automática do contexto. Agora o conflito tem estado separado dos erros de consulta: o refresh preserva a explicação, enquanto nova tentativa ou mudança de escopo a limpa. A pergunta e o novo fingerprint continuam preservados. O arquivo passou em Prettier e ESLint, e o retry passou no harness. A regressão está em `dashboard/web/tests/e2e/assistant-conflict.spec.ts`.

## Limites da evidência

Este QA verifica os fluxos e os contratos do frontend. A API sintética não valida parsers CSV/GPX/FIT, funcionamento de provedores externos, acurácia de IA ou composição de um ZIP real; esses pontos pertencem aos testes do backend e à integração. Os downloads desta rodada contêm somente bytes inventados. Não há anexos pessoais, capturas privadas ou resultados clínicos neste documento.
