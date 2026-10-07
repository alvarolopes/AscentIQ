# Plano de reformulação visual do AscentIQ

Data: 07/10/2026.
Status: estrutura boxed, topbar e padrão visual implementados e publicados localmente.
Revisão final solicitada: topbar de largura total da página; menu e conteúdo
permanecem boxed. Sidebar com altura natural; usuário à direita da topbar, com
dropdown para Conta e perfil, Dados e fontes e Sair. Esta revisão prevalece sobre
a composição inicial descrita abaixo.
Verificação: compilação frontend; navegação nas quatro áreas; menu e modal de
refeição no mobile (390px); boxed de 1440px no desktop, sem transbordamento.
Dropdown verificado no desktop e mobile; acesso ao perfil preservado.
Verificação final de backend: 25 testes direcionados passaram.

Pendência para a próxima sessão: escolher e configurar HTTPS confiável para
instalação da PWA no celular pela rede local. O suporte frontend foi publicado;
o endereço de rede ainda usa HTTP. Não há autorização de escolha de domínio
ou instalação de certificado nos dispositivos registrada até esta sessão.
Referência: quatro telas e dois guias visuais do arquivo `stitch_plataforma_digital.zip`.

## Direção aprovada pelo usuário

Usar o Stitch como inspiração, com liberdade para escolher a versão mais limpa.
Preservar o logo atual do AscentIQ. Manter o layout **boxed e centralizado**, sem
esticar o aplicativo por toda a largura de monitores grandes. Incluir a topbar
no projeto; o menu à esquerda fica boxed junto com o conteúdo.

Esta mudança reorganiza a apresentação. Mantém os dados, as integrações, os
cálculos e os fluxos existentes. As imagens do Stitch contêm valores ilustrativos
e funcionalidades sugeridas; não são uma fonte de dados nem uma nova especificação
funcional.

## O que aproveitar e o que simplificar

Aproveitar o fundo escuro, cards bem delimitados, hierarquia clara entre valor,
unidade e meta, botões agrupados perto do título e organização consistente dos
gráficos. O verde orienta ações principais e elementos selecionados. Azul pode
distinguir informações de sono. Textos secundários têm menor destaque, mantendo
contraste suficiente para leitura.

Eliminar a duplicação de navegação superior e lateral do protótipo. Preservar o
menu flutuante à esquerda com Dashboard, Workouts, Nutrition e Sleep. O nome do
usuário e o menu Conta e dados permanecem no rodapé do menu.

Manter uma topbar global, conforme o pedido mais recente, com o logo atual e um
status discreto de atualização. Ela não repete os quatro destinos do menu lateral.
Cada tela também tem seu cabeçalho de título, data/filtros e ações específicas.
Não copiar busca e notificações fictícias do protótipo.

Não incluir painéis laterais permanentes de dispositivos, publicidade de análise
de fotos, console de telemetria, busca global sem comportamento definido, sino de
notificações sem notificações reais ou novas subáreas apenas por constarem no HTML.
Explicações extensas ficam sob os ícones de informação ou nos modais existentes.

Não reproduzir afirmações ilustrativas sobre Apple Watch conectado, sincronização
BLE, bateria, calibração TACO/TBCA, fases de periodização, TSS oficial, adesão,
recuperação comprovada ou recomendações de sono calculadas. Só mostrar o que o
aplicativo realmente recebe ou calcula, com data e origem quando necessárias.

## Estrutura boxed

O limite de largura aplica-se ao **conjunto do aplicativo**, incluindo topbar, menu
lateral, espaço entre colunas e conteúdo. A topbar atravessa a largura do boxed;
abaixo dela, menu e conteúdo ficam lado a lado. Não limitar apenas os cards deixando
o menu preso à borda da tela.

Composição prevista:

```text
              conjunto centralizado, largura máxima 1440px
          ┌──────────────────────────────────────────────┐
          │ TOPBAR · logo atual · status de atualização  │
          ├───────────┬──────────────────────────────────┤
          │ MENU      │ Título · data/filtros · ações     │
          │ Dashboard │                                  │
          │ Workouts  │ Cards, gráficos e registros      │
          │ Nutrition │ da área selecionada              │
          │ Sleep     │                                  │
          │ Conta     │                                  │
          └───────────┴──────────────────────────────────┘
```

Proposta inicial de geometria:

| Elemento | Comportamento |
|---|---|
| Contêiner principal | `width: 100%`, `max-width: 1440px`, centralizado |
| Topbar | Mesma largura do boxed; cerca de 64px de altura; logo e status |
| Margens externas | 24–32px desktop; 16px mobile |
| Menu desktop | Aproximadamente 220px; acompanha a rolagem dentro do conjunto |
| Espaço entre menu e conteúdo | 24px |
| Coluna de conteúdo | Ocupa o restante do contêiner; `min-width: 0` |
| Cards | Espaçamento de 16–24px; padding de 20–24px |
| Tablet | Cards em duas colunas; menu recolhido quando faltar espaço |
| Celular | Menu em gaveta; cards em uma ou duas colunas conforme legibilidade |

Topbar e menu podem acompanhar a rolagem com posicionamento sticky, respeitando
o limite do conjunto e sem se sobrepor. No mobile, a topbar contém o botão de abrir
o menu em gaveta; o status pode ser reduzido a uma indicação curta e acessível.

O valor de 1440px é um ponto de partida para avaliação visual. O requisito é
manter a composição centralizada e limitada; ajustes da largura máxima não podem
resultar em uma interface full width. Gráficos, refeições e tabelas usam a largura
da coluna de conteúdo. Rolagem horizontal pertence ao componente que precisa dela,
sem criar rolagem lateral na página inteira.

## Identidade e componentes

Preservar o SVG de montanhas usado no componente `Peak`, a marca AscentIQ e suas
proporções. O raio do Stitch não entra na identidade. Aplicar o mesmo desenho aos
locais em que a marca aparece, inclusive ícones da PWA quando forem revisados.

Consolidar os estilos existentes em tokens: fundo, superfície, borda, texto,
texto secundário, verde principal, azul informativo, âmbar de atenção, erro,
espaçamento, raio e tipografia. Evitar sobrepor outro tema ao CSS antigo.

Base sugerida: fundo `#0d1117`, cards `#161b22`, bordas `#30363d`, texto
`#e6edf3`, secundário próximo de `#a3adb8`. Usar a paleta verde atual como base;
testar contraste dos botões antes de escolher um verde mais claro do Stitch.
Uma fonte sem serifa para toda a interface e números tabulares para métricas.
Inter pode ser usada se disponibilizada localmente; a interface não deve depender
de fontes ou scripts de CDN para funcionar.

Títulos de página compactos, aproximadamente 24–28px; métricas 28–36px;
texto de leitura 14–16px. Não adotar letras serifadas nas métricas vistas nas
capturas. Valores, unidades e metas devem continuar legíveis no mobile.

Componentes compartilhados: estrutura boxed, topbar, sidebar, cabeçalho de página, painel,
card de métrica, progresso, badge de estado, botão, campo, tabs, paginação, tooltip,
mensagem de estado e modal. Reaproveitar os componentes e gráficos existentes,
mantendo seus comportamentos.

## Plano por tela

### Dashboard

1. Cabeçalho com título, seletor de data e atualização. Ações de análise, check-in,
   objetivos e assistente em uma linha compacta que se reorganiza no mobile.
2. Quatro cards: alimentação, proteína, treino e sono. Valor destacado, unidade e
   meta secundárias; poucas palavras para indicar cobertura ou pendência.
3. Objetivo e check-in em cards menores. Justificativa do plano no modal, sem
   transformar o Dashboard em um relatório.
4. Calendário de frequência em um painel de largura completa **dentro do boxed**.
   Grade e meses centralizados; área rolável no celular.

O calendário mantém a regra recém-definida: de zero a quatro categorias por dia,
com um ponto para sono, alimentação, corrida e força. Várias refeições ou sessões
não aumentam o peso da categoria. Cinza sem categorias e verde mais escuro conforme
a quantidade aumenta. Tooltip com data e somente categorias presentes; os totais
de horas, calorias, distância e sessões permanecem. Não copiar a escala invertida
da imagem do Stitch. Não adicionar sequência ou adesão nesta mudança.

Progresso nutricional aparece quando há meta válida e dados suficientes. Pendência,
subtotal e ausência continuam distintos. Não mostrar zero ou saldo preciso quando
o valor é desconhecido. Ultrapassar uma meta não vira automaticamente um sinal de
sucesso nem um alerta clínico.

### Workouts

Manter apenas Visão geral, Corrida e Força. Tabs junto ao título, sem uma segunda
navegação lateral. Analisar treinos do dia abre o modal existente.

Na visão geral: objetivo esportivo curto, três métricas de fitness/fadiga/forma,
gráfico principal, resumo da semana e atividades recentes. Referências corporais
podem ficar em detalhes recolhidos para reduzir o volume inicial da tela.

Corrida e Força mantêm filtros, indicadores do período e listas paginadas. Detalhes
de exercícios e séries aparecem sob demanda. Identificar carga estimada sem
rebatizá-la como TSS oficial. Não criar barras percentuais para índices sem uma
meta ou escala que justifique a porcentagem.

### Nutrition

Cabeçalho com data e botão Adicionar refeição. Quatro cards de calorias e macros,
com valores e metas alinhados. Estado do diário e atualização da meta de forma
compacta; avisos que pedem ação permanecem visíveis.

Refeições em grid de duas colunas no desktop e uma no celular. Cada card apresenta
tipo de refeição, texto/foto existentes, resumo dos nutrientes, estado da estimativa
e ações já disponíveis. Evitar repetir o botão Adicionar refeição em vários locais.

Adicionar e editar continuam em modal. Salvar dispara a estimativa automaticamente.
Preservar pendência, falha, nova tentativa, cobertura do diário, edição e remoção
sem perda de dados. Estimativas não devem ficar com aparência de medição exata.

### Sleep

Cabeçalho curto, filtros de período, resumo de duração/pontuação/cobertura,
gráficos e registros. Duração e pontuação continuam medidas distintas. As médias
consideram o período todo, não somente a página atual.

Gráficos lado a lado no desktop e empilhados no mobile. Histórico com paginação
10/15; tabela com rolagem interna ou resumo em cards na tela pequena. Outras
medidas só aparecem se estiverem disponíveis na fonte. Não criar metas de sono,
arquitetura REM ou conclusões de recuperação a partir de elementos fictícios.

## Interações e estados preservados

- Todos os formulários e análises continuam nos modais definidos anteriormente.
- Modais preservam foco, Escape, retorno ao botão de origem e proteção de rascunhos.
- Assistente permanece flutuante no canto inferior esquerdo, com continuidade,
  minimizar/restaurar e contexto selecionado. Sua posição acompanha a margem do
  boxed no desktop e se adapta à tela no celular.
- Listas continuam com 10 registros por padrão e no máximo 15.
- Histórico e decisões, Saúde, Planejamento e Relatórios não voltam ao menu.
- Conta e dados mantém integrações, documentos, perfil, IA e sincronização.
- Atualização em segundo plano não apaga gráficos, cards ou tooltip nem perde foco.
- Estados vazios, parciais, carregamento inicial, erro e gravação são tratados
  explicitamente, sem demonstrar dados fictícios na plataforma pessoal.
- A oferta PWA continua acessível. HTTPS confiável ainda é uma dependência para
  concluir a instalação no endereço de rede local; o redesign não resolve essa
  configuração por si só.

## Ordem de implementação proposta

1. Consolidar os tokens e componentes básicos; remover regras CSS substituídas.
2. Montar o contêiner boxed, topbar, sidebar e cabeçalho, validando desktop e mobile.
3. Redesenhar Dashboard e calendário mantendo contagem e atualização atuais.
4. Aplicar o padrão a Nutrition, Workouts e Sleep.
5. Harmonizar modais, assistente, Conta e dados e convite de instalação.
6. Fazer revisão visual e funcional e só então publicar a mudança completa.

Os HTMLs do Stitch são referência visual, sem importar suas dependências, scripts
ou dados ilustrativos diretamente. Arquivos principais previstos: `style.css`,
`main.jsx`, `Health.jsx`, `Frequency.jsx`, `FoodDiary.jsx`, `Sleep.jsx`, `ui.jsx` e
componentes visuais compartilhados que forem extraídos. Alterações de backend só
se houver uma necessidade concreta de apresentação que os dados atuais não atendam.

## Critérios de aceitação

Avaliar em larguras de 360, 390, 768, 1024, 1440 e 1920px. Em 1920px, o conjunto
topbar/menu/conteúdo deve permanecer centralizado com margens visíveis. Nenhuma página
deve transbordar horizontalmente. O logo deve ser o atual.

Validar registro e edição de refeição, estimativa automática e pendente, check-in,
objetivos, análise diária e de treinos, assistente, fontes e paginação. Confirmar
que gráficos e totais não mudam ao trocar de página da lista.

Testar calendário com zero, uma e quatro categorias, refeições repetidas, sono sem
duração e refeições pendentes; tooltip por mouse, teclado e toque. Observar várias
atualizações automáticas para confirmar que não pisca.

Verificar contraste, foco, rótulos acessíveis, toque confortável, teclado virtual,
rolagem de modais e convivência do assistente com o convite PWA. Não usar apenas
cor para comunicar estado. Não adicionar animações contínuas ou indicadores
piscando.

Compilação frontend e verificações funcionais direcionadas devem passar. Capturas
de desktop e mobile devem evidenciar a composição final antes da publicação.
