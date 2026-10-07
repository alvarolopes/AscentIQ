# Interface simplificada da plataforma AscentIQ

Status: interface implementada e validada com dados sintéticos, inclusive em tela pequena.
Data: 06/10/2026.

## Objetivo

Simplificar a plataforma pessoal de saúde e fitness para quatro áreas principais,
reduzindo formulários permanentes, textos explicativos e seções de histórico.
O usuário deve conseguir entender seu dia, registrar informações e consultar a IA
com poucos cliques, mantendo os dados estruturados e as integrações existentes.

Esta implementação reorganiza a experiência. Não redefine as metas nutricionais,
os modelos de treinamento, os critérios de recuperação ou os cálculos existentes.
Os próximos locais de uso da IA serão definidos pelo usuário separadamente.

## Navegação

Menu principal flutuante à esquerda, com ícone e nome para apenas quatro opções:

1. Dashboard
2. Workouts
3. Nutrition
4. Sleep

O menu acompanha a rolagem sem cobrir o conteúdo. A área superior pode conter
título, data ou estado de atualização, mas não o menu principal.
Em telas pequenas, o menu da esquerda pode ser recolhido em uma gaveta.
Os quatro nomes acima permanecem como solicitados; os demais textos continuam em português.

Abaixo do nome do usuário, um menu secundário reúne:

- Dados e fontes: integrações, importações, sincronização, configuração da IA,
  estado das fontes e controles operacionais existentes.
- Perfil e medidas: informações pessoais necessárias aos cálculos e registro de peso.
- Sair.

O botão de atualização dos treinos fica em Dados e fontes, com indicação discreta
de andamento disponível durante a navegação.

## Dashboard

Página inicial com a data selecionada e um resumo curto dos dados disponíveis:

- Alimentação: calorias e proteína registradas em relação às metas.
- Treino: atividades e carga disponíveis para o dia.
- Sono: duração e indicadores disponíveis, identificando a data de referência.
- Objetivo principal: resumo curto e acesso ao plano vigente.
- Check-in: situação do registro do dia.

Dados ausentes permanecem identificados como ausentes, sem gerar valores inventados.
O resumo não deve reproduzir longas análises ou formulários completos.

Ações disponíveis:

- Analisar meu dia: abre modal com a análise, relato opcional e controles de geração.
- Registrar/editar check-in: abre modal do registro do dia selecionado.
- Objetivos: abre modal com objetivos e plano vigente.
- Assistente: abre a janela flutuante de conversa.

O aviso explicativo "Como ler esse dia" deixa de ocupar um bloco permanente.
Um botão de informação com rótulo acessível abre o texto por clique.
Avisos explicativos podem ficar sob esse ícone; erros de gravação, indisponibilidade
e alterações não salvas continuam visíveis quando exigem uma ação.

## Workouts

Subáreas permitidas: Visão geral, Corrida e Força.

### Visão geral

Mantém resumos e gráficos úteis de volume, carga, fitness, fadiga e forma.
As explicações de método ficam atrás de ícones de informação ou detalhes solicitados.
A análise diária de treinamento deixa de ser uma aba ou seção permanente:
um botão na Visão geral abre seu modal, preservando a capacidade atual de consultar
e gerar a análise de treino.

A análise de treinamento e a análise geral do dia têm escopos distintos.
A primeira interpreta os treinos; a segunda reúne alimentação, treino, horário
e recuperação. Não devem ser apresentadas como resultados equivalentes.

### Corrida e Força

Mantêm indicadores e filtros de período pertinentes à modalidade.
Históricos, sessões, provas e tabelas de exercícios/séries obedecem à paginação.
Detalhes de uma sessão podem ser abertos sob demanda sem expandir toda a página.

Planejamento, Relatórios e seus atalhos de PDF saem da interface por enquanto.
Registros, arquivos, rotinas e serviços existentes não são apagados ou interrompidos
apenas por remover esses acessos da navegação.

## Nutrition

A página apresenta a data e o progresso diário em relação às metas:
calorias, proteína, carboidratos e gorduras.

O formulário de refeição deixa de aparecer permanentemente.
O botão Adicionar refeição abre um modal com descrição, tipo de refeição e foto,
conforme as capacidades existentes.

Ao salvar, a refeição é registrada e a estimativa pela IA é solicitada automaticamente.
Não haverá um segundo botão obrigatório para analisar a refeição.
O modal mostra andamento e falhas; a página distingue pendente, concluída e erro.
Uma falha de IA não pode apagar o registro nem duplicar a refeição em uma tentativa posterior.

As refeições do dia aparecem em um grid responsivo de cards:

- Nome/tipo da refeição e descrição resumida.
- Foto, quando cadastrada.
- Calorias e macros estimados, com estado da estimativa.
- Editar e remover; editar abre o mesmo modal com os dados preenchidos.

O grid também é paginado. Após salvar ou editar, os totais e os cards são atualizados
sem recarregar toda a plataforma.
O estado de cobertura alimentar permanece acessível: diário parcial, completo
ou declaração existente de jejum. Ele não é substituído pela quantidade de cards.

Histórico de alterações, restauração e decisões saem da tela, mas continuam armazenados.
A análise geral do dia pode ser acessada por botão nesta área usando o mesmo modal
do Dashboard, sem duplicar relatórios ou controles.

## Sleep

Área principal independente, mantendo os filtros de período, resumos, gráficos
e registros de sono disponíveis.
O histórico por dia fica paginado. Médias e gráficos usam o período filtrado inteiro,
e não apenas os registros da página atual.
Uma data sem registro não é interpretada como uma noite sem dormir.

## Objetivos em modal

Objetivos deixam de ser uma opção do menu principal.
O botão no Dashboard abre um modal para consultar o objetivo principal, o plano vigente,
as metas e os controles atuais de criação/edição e estado dos objetivos.

O controle de meta alimentar automática continua acessível nesse modal.
Justificativa e limitações do plano ficam disponíveis sob demanda.
Histórico de planos e decisões deixa de ser exibido.
A lista de objetivos, quando necessária, também fica paginada.

## Assistente flutuante

O botão no Dashboard abre um painel de conversa no canto inferior esquerdo,
posicionado para não cobrir o menu principal.
Apesar de ter sido chamado de modal no pedido, seu comportamento é não bloqueante:
não há fundo escurecido, bloqueio da página ou captura exclusiva do teclado.

Permite minimizar, fechar o painel e continuar usando o site, inclusive mudar de área,
sem perder a conversa ou o rascunho. Em dispositivos pequenos, pode ocupar uma área
maior recolhível, mantendo o acesso à navegação ao ser minimizado.

O assistente deve conseguir responder sobre o dia, mês, períodos definidos e objetivos,
com acesso ao contexto relevante disponível: perfil, peso e medidas, objetivos,
plano vigente, refeições, cobertura alimentar, treinos, carga, sono, check-ins e fontes.
Referências e documentos pessoais existentes podem ser consultados quando relevantes
à pergunta; credenciais, tokens e segredos técnicos nunca entram no contexto da IA.

O seletor de contexto oferece Dia, Mês, Objetivos, Últimos dias e Período definido.
O mês segue o calendário real; o mês atual termina na data atual. Períodos
personalizados aceitam de 1 a 90 dias. Objetivos usa as referências vigentes
na data escolhida e apresenta o intervalo de acompanhamento utilizado.

"Acesso a todo o contexto" significa consultar os registros pertinentes ao escopo,
sem enviar a base inteira em toda pergunta. Totais e resumos usam o período inteiro;
detalhes recentes são selecionados e suas quantidades são informadas na interface.
Se o contexto exceder o limite do modelo, séries extensas podem virar resumos do
período, preservando totais, cobertura e indicação dessa seleção. Força inclui
nomes de exercícios e totais, sem enviar todas as séries. Para consultar um detalhe
antigo, selecione sua data. O modo Mês não equivale aos últimos 14 ou 30 dias.

Perguntas seguintes consideram trechos de até três respostas recentes da mesma
conversa; a conversa completa fica salva e consultável por páginas. Novas mensagens
consultam dados atualizados sem apagar as respostas anteriores. Referências médicas
e documentos exigem seleção explícita em Contexto e opções. Ao desativá-la,
respostas anteriores que continham dados médicos não voltam ao contexto da IA.
O assistente explica e sugere; sua resposta não altera automaticamente refeições,
objetivos, planos ou atividades.
O uso local de Ollama permanece disponível, sem introduzir uma API paga obrigatória.

## Paginação global

Padrão implementado: 10 registros por página, com opção de 15. Nunca mais de 15.
Aplica-se a tabelas, listas de registros, grids e históricos que continuarem acessíveis,
inclusive em modais, Dados e fontes e detalhes de sessões.
Conversas antigas podem ser consultadas em páginas, preservando a continuidade
e o rascunho da conversa atual.

- Controles de anterior/próxima, página atual e total de registros.
- Busca, ordenação e filtros operam sobre todos os registros pertinentes.
- Alterar um filtro retorna à primeira página.
- Excluir o último registro de uma página ajusta para uma página válida.
- Totais, gráficos e médias não são limitados à página visível.
- "Mostrar mais" acumulando dezenas de itens na mesma tela é substituído por paginação.
- O histórico do assistente usa consulta paginada no servidor. Os demais painéis
  paginam os registros carregados de seu snapshot ou consulta, mantendo resumos
  do período inteiro. Ampliar a paginação no servidor para outras coleções é uma
  evolução de desempenho quando o volume exigir.

## Dados preservados e acessos removidos

Saem da navegação: Saúde, Objetivos, Assistente, Planejamento e Relatórios.
Saem dos blocos permanentes: análises, formulários de check-in e refeição,
textos explicativos extensos, histórico e decisões.

Permanecem: dados de saúde e medidas, documentos, fontes, versões de planos,
decisões, trilhas de alterações, relatórios já gerados e integrações.
Remover uma tela não significa excluir os dados ou retirar contexto do assistente.
Perfil e peso seguem editáveis pelo menu secundário do usuário.

## Organização da implementação

- `main.jsx`: menu, acessos do usuário, subáreas de Workouts, modais principais e
  janela persistente do assistente.
- `ui.jsx`: modal com foco, Escape seguro, confirmação de descarte e retorno ao
  botão de origem; ícone de informação e paginação comum de 10/15 registros.
- `Health.jsx`: Dashboard compacto, check-in em modal, perfil e medidas editáveis.
- `Goals.jsx`: objetivos e plano vigente dentro do modal, justificativa sob demanda
  e propostas pendentes sem arquivo de decisões.
- `FoodDiary.jsx`: refeições em grid paginado, formulário em modal e estimativa
  automática preservada ao salvar.
- `DayReview.jsx` e `DailyAnalysis.jsx`: análises geral do dia e de treinamento,
  respectivamente, abertas sob demanda e com proteção da operação em andamento.
- `Sleep.jsx`: sono como área principal, com registros paginados e resumos completos.
- `Assistant.jsx` e serviços de contexto: períodos explícitos, continuidade da
  conversa, atualização antes de perguntar e histórico paginado no servidor.

Os critérios abaixo orientam a validação integrada no navegador, inclusive em tela
pequena. O status de implementação não substitui evidência de teste de cada fluxo.

## Critérios de conclusão

- Menu principal à esquerda contendo apenas Dashboard, Workouts, Nutrition e Sleep.
- Dados e fontes acessível abaixo do nome do usuário.
- Nenhuma coleção de registros exibe mais de 15 itens na mesma página.
- Formulários, análises e objetivos são abertos pelas ações previstas.
- Informação sobre interpretação do dia aparece somente após clicar no ícone.
- Refeições são cards em grid; salvar continua acionando a IA automaticamente.
- Workouts contém somente Visão geral, Corrida e Força.
- Saúde, Planejamento e Relatórios não aparecem como áreas da interface.
- Históricos e decisões continuam armazenados, sem seus painéis atuais.
- Assistente permite usar e navegar no site enquanto a conversa permanece aberta.
- Perfil e peso continuam editáveis, sem depender da antiga aba Saúde.
- Filtros, totais e gráficos continuam corretos com a paginação.
- Modais têm título, foco inicial, navegação por teclado, fechamento por Escape
  quando seguro e retorno do foco ao botão de origem.
- Rascunhos não são descartados silenciosamente; salvar em andamento não permite
  envio duplicado nem fechamento que perca o estado da operação.
- Nenhuma etapa apaga registros existentes ou exige cobrança por chamada de IA.

## Pendências para futuras decisões

- Novos pontos de uso de IA, além dos recursos já existentes e do assistente solicitado.
- Detalhes visuais finais, mantendo a estrutura e os comportamentos definidos acima.
- Decidir posteriormente se Planejamento e Relatórios retornam em alguma forma.
- Expandir a paginação no servidor para outras coleções quando o volume de dados exigir.
