# SPEC — Plataforma individual de saúde e fitness

**Versão:** 1.0
**Data:** 2 de outubro de 2026
**Natureza:** especificação de produto, funcionalidades e comportamento esperado
**Nome de trabalho:** AscentIQ — nome revisável
**Público inicial:** uma pessoa acompanhando a própria saúde, alimentação e atividade física

## 1. Para que serve este documento

Esta SPEC descreve a ideia completa do produto, o que já existe como ponto de partida e o que queremos alcançar. Deve permitir que outra IA ou equipe construa a plataforma do zero, sem acesso às conversas anteriores e sem precisar reproduzir a arquitetura atual.

A implementação existente é uma referência de aprendizado. Linguagens, banco de dados, frameworks, provedor de IA, forma de hospedagem e organização do código podem mudar. O compromisso é com os comportamentos, a confiabilidade dos dados e a experiência descritos aqui.

O produto deve funcionar tanto numa instalação vazia quanto com uma história anterior fornecida pelo usuário. Requisitos de preservação e migração da base atual são condicionais à entrega dessa base; os requisitos de funcionamento e os testes sintéticos independem dela.

O pedido que orienta o produto é:

> Quero uma plataforma individual de saúde e fitness. Ela deve ler dados de relógios e importar plataformas, registrar alimentação e usar IA para estimar calorias, calcular o déficit calórico, permitir definir um objetivo e adaptar a orientação ao longo do tempo. Quero reunir meus dados, guardá-los de forma estruturada e usar inteligência para me ajudar.

Os requisitos estão organizados em três níveis:

- **P0 — núcleo obrigatório:** necessário para entregar esse ciclo completo, do registro à adaptação.
- **P1 — ampliação:** melhora a experiência e aprofunda capacidades, depois de estabilizar o núcleo.
- **P2 — evolução opcional:** possibilidades futuras; não são condição para a primeira entrega.

As funcionalidades futuras são propostas de produto derivadas do pedido. Não devem ser confundidas com funcionalidades já implementadas ou decisões já aprovadas sobre tecnologia.

## 2. Visão do produto

A plataforma deve funcionar como uma memória pessoal de saúde e fitness, atualizada continuamente, capaz de transformar registros dispersos em uma visão útil da pessoa e de seus objetivos.

O usuário não deveria precisar reconstruir sua história toda vez que conversa com uma IA. Treinos, refeições, sono, medidas corporais, preferências, avaliações, metas e decisões anteriores devem compor um contexto persistente e consultável.

O ciclo central é:

**Coletar → organizar → conferir → calcular → interpretar → propor ajustes → acompanhar o resultado.**

A plataforma precisa responder a perguntas como:

- O que aconteceu comigo hoje e nesta semana?
- Quanto comi, quanto provavelmente gastei e quão confiável é essa estimativa?
- Estou progredindo em direção ao meu objetivo?
- Minha alimentação está coerente com minha carga de treino e recuperação?
- O que mudou em relação ao meu histórico?
- Há dados suficientes para ajustar o plano ou preciso registrar melhor alguma coisa?
- Qual ajuste faz sentido agora e por quê?

O produto começa individual, com profundidade no histórico de uma pessoa. Contas de profissionais, comunidade, ranking, monetização e gestão de vários pacientes não fazem parte do núcleo inicial.

## 3. O que já temos

O projeto começou como um sistema pessoal de análise esportiva, especialmente corrida, trail, endurance e montanha. Evoluiu para um portal privado que reúne outras dimensões de saúde.

A tabela abaixo descreve capacidades encontradas na documentação e no código local em `athlete-agent`. Indica existência de implementação, sem certificar que todas as integrações estejam autenticadas ou que todos os serviços estejam em execução neste momento.

| Área | Capacidade existente | Limite atual relevante |
| --- | --- | --- |
| Perfil e memória | Perfil do atleta, preferências, contexto, histórico esportivo, metas e referências corporais/nutricionais estruturados | Parte da manutenção depende de arquivos ou operações técnicas; não há um fluxo completo de edição do perfil pelo usuário |
| Integração Garmin | Importação e sincronização de atividades e sono; rotinas salvas também têm importadores | Leitura ocorre pela plataforma e pelos arquivos, sem conexão direta genérica com qualquer relógio |
| Integração Hevy | Importação de musculação com exercícios, séries, repetições, carga e RPE quando presentes | Cobertura depende dos registros disponíveis na origem |
| Histórico e arquivos | Uso de exportações Garmin/Strava, FIT, GPX e CSV; análise de rotas, provas e sessões | Importar exportações Strava não equivale a ter um conector contínuo Strava completo |
| Consolidação | Vínculo entre registros Garmin e Hevy da mesma sessão para evitar contar duas vezes | A contribuição de sessões somente Hevy ao modelo de carga ainda é limitada |
| Treino e desempenho | Volume, distância, duração, elevação, frequência cardíaca, comparações históricas e índices de execução/desempenho | Alguns índices são personalizados ao contexto esportivo original |
| Carga | Modelo próprio de Fitness, Fatigue e Form, com referências de 42 e 7 dias | São estimativas de carga, não diagnóstico, percentual de condicionamento ou TSS oficial |
| Sono | Histórico diário, duração, pontuação, gráficos, filtros e preservação de registros anteriores | Não representa recuperação comprovada nem cobertura garantida de todos os sinais do relógio |
| Corpo | Consulta de peso, gordura corporal, massa magra, perimetria e dobras, com datas de avaliação | Não há um diário completo de medidas com cadastro cotidiano pela interface |
| Exames | Consulta de resultados e contexto previamente estruturados, com documentos privados | Não há um fluxo geral completo de envio e extração automática de qualquer exame |
| Alimentação | Registro por texto, estimativa de calorias e macros por IA, revisão antes de salvar e totais diários | Não há entrada por foto ou voz; correção de refeição salva exige excluir e registrar novamente |
| IA diária | Análise sob demanda de treinos, força, carga recente e sono; opção de importar resposta de outra IA | Não é ainda um assistente integrado de toda a saúde, alimentação, energia e objetivos |
| Objetivos | Objetivos e referências são lidos da memória estruturada; o objetivo esportivo ativo aparece no portal | Não existe motor completo de definição, acompanhamento e adaptação de objetivos |
| Relatórios | Painel interativo, relatórios datados em HTML/PDF e histórico de execuções | O PDF atual é restrito a dados de treino; alimentação e análise diária têm armazenamento próprio |
| Persistência | Implementação de banco versionado, dados normalizados, revisões, arquivos originais e cálculos reproduzíveis | Nem todos os módulos usam a mesma camada: alimentação e análises diárias também persistem em arquivos privados |
| Operação | Atualizações manuais/agendadas, estados de execução, tratamento de atualização parcial e backups privados | A execução local depende do computador e dos serviços ativos |
| Privacidade | Autenticação, acesso local privado, proteção de credenciais e separação entre dados pessoais e código público | Acesso seguro pelo celular fora do computador ainda exige uma solução de implantação |

### 3.1 O que ainda falta para a visão completa

- Um perfil pessoal e objetivos editáveis pela própria interface.
- Uma experiência integrada de saúde, treino, alimentação e progresso.
- Um balanço energético diário e por período, com fontes e incerteza explícitas.
- Distinção operacional entre diário alimentar parcial e dia declarado completo.
- Metas e recomendações que se ajustam a tendências reais e à qualidade dos dados.
- Conversa com IA usando o contexto selecionado da pessoa e preservando decisões úteis.
- Entrada alimentar por imagem e, posteriormente, voz.
- Registro simples de medidas, check-ins e correções, sem depender de edição de arquivos.
- Uso confortável no celular e maior autonomia em relação a uma sessão externa de IA.
- Exportação de todo o contexto de forma que a pessoa possa migrar de sistema ou de IA.

### 3.2 O aprendizado que devemos preservar

O produto já demonstrou que dados pessoais dispersos podem virar uma memória estruturada, que fontes diferentes podem ser consolidadas e que análises melhoram quando conhecem a história e a intenção do usuário.

A evolução amplia esse princípio para a saúde individual. Corrida e montanha continuam suportadas, mas deixam de determinar as metas de todos os usuários ou de todas as fases da mesma pessoa. Um objetivo concluído deve tornar-se histórico; a plataforma precisa reconhecer a prioridade atual.

## 4. Objetivos e critérios de sucesso do produto

| Objetivo | O que precisa acontecer para considerá-lo atendido |
| --- | --- |
| Centralizar os dados | O usuário encontra atividades, refeições, sono, medidas e objetivos numa história pessoal coerente, com origem e datas |
| Reduzir trabalho manual | Fontes conectadas atualizam os dados; registros cotidianos podem ser feitos sem conhecimento técnico |
| Tornar a alimentação utilizável | Uma refeição descrita vira itens e estimativas revisáveis que alimentam totais e balanço energético |
| Acompanhar um objetivo | A meta tem ponto de partida, critérios, prioridade e progresso observável |
| Adaptar a orientação | Novos registros podem gerar propostas justificadas de ajuste; pouca evidência leva a manter o plano ou pedir dados melhores |
| Tornar a IA pessoal | Respostas usam o histórico pertinente, mostram a base da interpretação e lembram decisões confirmadas |
| Manter confiança | Falta de dado, estimativa, falha de integração e conflito não aparecem como certeza ou sucesso completo |
| Preservar a autonomia | O usuário consegue corrigir dados, entender mudanças, reverter ajustes e exportar sua história |

Indicadores operacionais a acompanhar: tempo para registrar uma refeição, sucesso e atraso por integração, duplicatas pendentes, cobertura dos diários, frequência de correções, utilização das análises e compreensão dos ajustes propostos. Metas numéricas desses indicadores devem ser definidas após observar o uso real.

## 5. Princípios obrigatórios

1. **Histórico persistente:** a pessoa não precisa recontar sua vida a cada análise.
2. **Dado antes de interpretação:** fatos registrados, cálculos, hipóteses da IA e decisões do usuário são categorias distintas.
3. **Ausência não significa zero:** sem refeição não significa jejum; sem treino não significa descanso; sem sono não significa noite sem dormir.
4. **Uma realidade, várias fontes:** dois dispositivos podem descrever a mesma sessão sem criar duas sessões reais.
5. **Objetivos explícitos:** recomendações devem respeitar a prioridade e as restrições atuais, incluindo conflitos entre objetivos.
6. **Estimativas transparentes:** calorias, gasto, recuperação e prontidão não devem aparentar uma precisão que os dados não sustentam.
7. **Adaptação verificável:** toda mudança tem motivo, evidência, versão e possibilidade de revisão.
8. **Uso cotidiano simples:** adicionar dados e entender o dia deve funcionar bem no celular.
9. **Privacidade por padrão:** a base pessoal é privada; compartilhar ou enviar contexto externo é uma ação controlada.
10. **Independência técnica:** o contexto pertence ao usuário e pode sobreviver à troca de banco, aplicação ou provedor de IA.

## 6. Jornadas principais

### J1. Começar a usar

O usuário cria seu perfil, informa preferências e unidades, conecta uma primeira fonte ou importa arquivos, registra um objetivo e vê o que foi coletado. O sistema explica quais áreas têm dados e quais ainda estão vazias. Campos essenciais são solicitados conforme a função que depende deles, sem exigir todo o histórico para começar.

### J2. Atualizar relógio e plataformas

O relógio sincroniza com sua plataforma de origem. A aplicação importa o que estiver disponível, liga registros equivalentes, preserva o histórico e mostra a atualização por fonte. Uma falha no Garmin não apaga o Hevy; uma falha no relatório não apaga os dados já armazenados.

### J3. Registrar uma refeição

O usuário descreve o que comeu e as quantidades. A IA sugere itens, calorias, macros e hipóteses. O usuário corrige e salva. A refeição passa a integrar o total daquele dia. Repetir a tentativa de salvar não cria uma segunda refeição. Na ampliação por foto, a imagem segue o mesmo fluxo de estimativa e revisão.

### J4. Entender o dia

O usuário abre a visão diária e encontra alimentação registrada, gasto estimado disponível, estado do balanço energético, atividades, sono e check-in. Vê o que ainda é parcial e recebe uma leitura contextual, com acesso aos registros usados.

### J5. Acompanhar e adaptar um objetivo

O usuário escolhe, por exemplo, reduzir gordura preservando desempenho. A plataforma acompanha tendência corporal, alimentação, treino e recuperação. Na revisão do período, propõe manter ou ajustar metas e explica o motivo. A versão anterior continua consultável.

### J6. Corrigir e migrar

O usuário corrige uma porção, desfaz a vinculação de duas atividades, muda uma medida ou exporta seus dados. O sistema recalcula os resultados afetados e marca análises antigas que dependiam de dados alterados. A exportação permite a outra aplicação ou IA compreender os registros e o estado do objetivo.

## 7. Perfil pessoal e contexto — P0

**RF-01 — Perfil editável.** Permitir cadastrar e atualizar identificação de uso, data de nascimento quando necessária, altura, fuso horário, unidades e demais características exigidas pelo modelo escolhido. Dados fisiológicos só devem ser pedidos quando têm finalidade clara no cálculo ou na interpretação.

**RF-02 — Preferências e restrições.** Registrar modalidades praticadas, disponibilidade semanal, rotina, equipamentos, preferências alimentares, alimentos evitados, alergias declaradas, restrições informadas e prioridades pessoais. Distinguir preferência de restrição clínica registrada.

**RF-03 — Memória contextual.** Preservar histórico relevante, decisões confirmadas, objetivos anteriores, eventos importantes e orientações profissionais que o usuário decidiu guardar. Cada informação deve ter origem, data e validade quando aplicável.

O sistema deve separar:

- Dados medidos ou importados.
- Informações declaradas pelo usuário.
- Referências extraídas de documentos e revisadas.
- Resultados de cálculo.
- Hipóteses e recomendações geradas pela IA.

Uma sugestão da IA não vira fato de perfil automaticamente. Informações antigas podem ser substituídas como referência ativa sem desaparecer do histórico. Metas, limiares, preferências e restrições precisam de vigência para que análises históricas usem o contexto correspondente à época.

## 8. Relógios, plataformas e arquivos — P0

**RF-04 — Conectar e importar.** Suportar coleta por plataformas, dispositivos acessíveis e importação de arquivos. Para o núcleo, priorizar Garmin e Hevy, além de aproveitar o histórico já exportado. O produto deve funcionar também com registros manuais quando a fonte automática não estiver disponível.

“Ler relógios” pode ser atendido por sincronização com a plataforma do fabricante. Comunicação direta com hardware é uma opção de implementação, não uma exigência universal.

### 8.1 Fontes e prioridade

| Fonte ou meio | Papel | Prioridade |
| --- | --- | --- |
| Garmin ou fonte equivalente de wearable | Atividades, sono e sinais diários disponíveis | P0: ao menos um conector funcional; Garmin é a referência inicial |
| Hevy | Musculação detalhada | P0 para preservar o caso de uso atual |
| FIT, GPX e CSV | Histórico, rotas e importação independente de conexão contínua | P0: resumo de atividade FIT, percurso GPX e modelo CSV documentado de atividades |
| Exportação Strava existente | Recuperar e reconciliar histórico de atividades | P0 condicional à migração quando esse histórico for fornecido; conector contínuo é P1 |
| Registro manual | Atividades, medidas, alimentação e check-ins | P0 |
| Fotos de refeições | Estimativa visual assistida | P1 |
| Health Connect, Apple Health, Polar, Suunto, Coros, balanças e outras plataformas | Ampliar cobertura conforme necessidade | P1/P2, sujeitos às possibilidades reais de acesso |
| TCX, outros arquivos e bases alimentares | Ampliar interoperabilidade | P1/P2 |

Essa lista não afirma que todas as plataformas ofereçam acesso a todos os dados. A implementação deve verificar disponibilidade, permissões, custo e cobertura de cada integração antes de prometer uma capacidade na interface.

Os contratos de importação P0 devem incluir exemplos sintéticos e regras para campos ausentes. O FIT deve extrair o resumo da sessão e as métricas realmente presentes. O GPX deve permitir consultar o percurso; um arquivo de rota sem evidência de execução não vira treino realizado. O CSV deve ter modelo publicado com identificação, data/horário, modalidade e duração, além de campos opcionais como distância, elevação e frequência cardíaca. Variações de exportação de fornecedores são adaptadores adicionais, não substituem o modelo documentado.

### 8.2 Comportamento da sincronização

**RF-05 — Atualização incremental confiável.**

- Importar o histórico inicial por intervalos controlados e mostrar progresso.
- Atualizar depois somente o necessário, com uma janela de revisão para dados atrasados ou corrigidos.
- Permitir atualização manual e agendamento configurável.
- Mostrar último sucesso, intervalo coberto, atraso, erro e necessidade de reconexão por fonte.
- Registrar a origem e o identificador externo de cada observação.
- Preservar os registros válidos quando uma fonte falha ou retorna campos vazios.
- Tratar remoção confirmada de origem separadamente de ausência numa resposta parcial.
- Retomar trabalhos interrompidos e evitar execuções concorrentes incompatíveis.
- Apresentar estados: em espera, em execução, sucesso, parcial, falha ou cancelado.
- Permitir reprocessar um intervalo sem duplicar registros.

O sucesso de uma fonte não autoriza exibir “tudo atualizado” quando outra falhou. Desconectar uma integração interrompe novas coletas; apagar o histórico é uma ação diferente.

### 8.3 Consolidação e conflitos

**RF-06 — Uma sessão canônica com evidências de várias fontes.**

Ao receber o mesmo treino de Garmin, Hevy ou Strava, o sistema deve procurar correspondências por identificadores, horário, modalidade, duração e outros sinais disponíveis. Correspondências claras podem ser vinculadas automaticamente; casos ambíguos ficam pendentes de revisão.

É obrigatório:

- Preservar os registros originais e a razão da vinculação.
- Definir uma preferência por campo, em vez de escolher sempre uma fonte para tudo.
- Usar, por exemplo, exercícios do Hevy e frequência cardíaca do Garmin na mesma sessão.
- Não somar duas vezes sessão, duração, calorias ou carga correspondentes ao mesmo esforço.
- Não unir atividades diferentes apenas porque ocorreram no mesmo dia.
- Permitir desfazer uma união e corrigir a preferência de fonte.
- Manter conflitos visíveis e recalcular o que depender da correção.

## 9. Atividades, treino e recuperação — P0/P1

**RF-07 — Diário de atividades multimodal.** Corrida, caminhada, trail, musculação, natação, ciclismo, escada, montanhismo e outras modalidades devem caber na mesma história, sem exigir métricas que não façam sentido para a modalidade.

Dados possíveis: data/hora, duração total e em movimento, distância, elevação, frequência cardíaca, potência, ritmo, calorias declaradas pela fonte, percurso, voltas, intenção, percepção de esforço e notas. Ausências devem permanecer explícitas.

Para força: exercícios, séries, repetições, carga, tipo de série, duração, RPE e notas quando disponíveis. Carga externa, estímulo muscular e esforço cardiovascular não são equivalentes.

**RF-08 — Visões de evolução.** Oferecer filtros por data e modalidade, resumos semanais, detalhes de sessões e comparação com períodos semelhantes. Comparar ritmo ou eficiência considerando terreno e contexto; não concluir melhora apenas por um número isolado.

**RF-09 — Carga e recuperação.** Mostrar tendências de carga e combinar, de forma explicável, sinais de treino, sono e percepção subjetiva. O modelo atual de Fitness/Fatigue/Form pode ser reutilizado ou substituído. Em ambos os casos, documentar entradas, fórmula, limitações e versão.

Requisitos adicionais:

- Distinguir dado ausente de descanso declarado.
- Explicar quais modalidades entram em cada métrica de carga.
- Não apresentar força sem frequência cardíaca como atividade sem esforço.
- Não exigir uma única pontuação para resumir toda a saúde da pessoa.
- Separar a medição do relógio da interpretação de recuperação.

**P1:** planejamento de treinos, sessões previstas versus realizadas, calendário de provas/eventos, análises de percurso e orientação específica para endurance/montanha. As capacidades atuais de análise histórica devem continuar migráveis, mesmo que a primeira interface reconstruída seja mais simples.

Enviar treinos para relógios, alterar agendas externas ou publicar atividades não faz parte da leitura inicial de integrações.

## 10. Sono, corpo e saúde — P0/P1

**RF-10 — Histórico de sono.** Guardar registros datados com duração, pontuação, estágios e demais sinais realmente fornecidos. Mostrar cobertura, lacunas e tendências. Pontuação ausente não invalida uma duração disponível.

Cada registro deve preservar a convenção da fonte para a data da noite. A interface precisa permitir entender a qual período o sono se refere, especialmente quando o treino acontece depois ou cruza a meia-noite.

**RF-11 — Medidas corporais.** Permitir registrar e importar peso, cintura, outras medidas e composição corporal. Guardar método, unidade, data e observações. Mostrar pontos reais e tendências identificadas como cálculo.

- Uma avaliação antiga não representa automaticamente o corpo de hoje.
- Medidas de protocolos diferentes não devem parecer diretamente equivalentes.
- Peso, gordura estimada e massa magra precisam de tratamento separado.
- Correções preservam rastreabilidade e recalculam tendências e objetivos.

**RF-12 — Check-in pessoal.** Registro rápido de disposição, fome, percepção de recuperação, estresse, dor/desconforto e notas, com opção de pular campos. Escalas devem ser consistentes ao longo do tempo e ter significado claro.

**RF-13 — Documentos e referências de saúde.** Guardar documentos privados, observações estruturadas e contexto informado, mantendo a distinção entre resultado de exame, referência, relato e conclusão profissional.

Na primeira entrega, permitir consultar referências de saúde e preservar o acervo anterior quando ele for fornecido. Uma instalação vazia pode começar sem documentos. Envio de novos documentos e extração assistida por IA são P1. Uma extração deve ser revisável, registrar página/origem, unidade e data, e nunca substituir o documento original.

A IA pode ajudar a organizar e contextualizar informações, mas não deve transformar um resultado isolado em diagnóstico ou alterar medicação. Dados clínicos são incluídos em uma análise externa somente dentro do escopo autorizado pelo usuário.

## 11. Alimentação e estimativa com IA — P0

**RF-14 — Diário alimentar editável.** Registrar refeições por data/hora e tipo, com descrição, itens, quantidades e notas. Permitir editar depois de salvar, excluir/desfazer, copiar uma refeição frequente e corrigir porções sem refazer o dia inteiro.

Permitir salvar apenas a descrição para analisar depois, inclusive quando a IA falhar. Esse registro fica com estimativa pendente: preserva a ocorrência da refeição, mas não entra no total conhecido como zero. A interface mostra que há consumo registrado ainda sem valor nutricional utilizável.

O núcleo deve funcionar com texto e cadastro manual. Exemplo de entrada:

> Almoço: arroz cozido, feijão, frango grelhado e salada. Usei uma colher de azeite. Não sei o peso do frango.

**RF-15 — Estimativa alimentar estruturada.** A IA transforma a descrição em uma proposta com:

- Alimentos identificados e quantidade/unidade interpretada.
- Calorias estimadas e, quando possível, proteínas, carboidratos e gorduras.
- Hipóteses sobre porção, preparo, óleo, peso cru/cozido e ingredientes incertos.
- Origem do valor: informado pelo usuário, rótulo, base alimentar ou estimativa de IA.
- Incerteza por item ou refeição, expressa de forma compreensível.
- Perguntas relevantes quando a falta de informação altera materialmente o resultado.

A ausência de quantidade não deve bloquear todo registro. Pode gerar uma estimativa com hipótese explícita, que o usuário corrige. Números nutricionais desconhecidos permanecem desconhecidos; não devem virar zero apenas para completar um formulário.

### 11.1 Fluxo de registro

1. Informar data, refeição e descrição.
2. Pedir a estimativa ou preencher valores manualmente.
3. Revisar itens, porções, calorias, macros e hipóteses.
4. Salvar uma versão confirmada.
5. Atualizar totais, cobertura do diário e resultados dependentes.

O rascunho gerado pela IA não entra nos totais até ser salvo. Uma nova análise não pode sobrescrever silenciosamente correções humanas. Valores inválidos e respostas malformadas devem ser rejeitados sem perder o rascunho útil.

### 11.2 Regras de confiança

- Uma foto não comprova o peso dos alimentos nem revela ingredientes invisíveis.
- Não inventar valores exatos de uma marca ou rótulo que não foi informado.
- Validar números, unidades e consistência antes de aceitar a estimativa.
- Não considerar a relação entre macros e calorias uma igualdade perfeita em todos os alimentos; diferenças precisam de explicação, não correção cega.
- Não converter toda resposta da IA em valor exato com casas decimais excessivas.
- Distinguir uma resposta importada pelo usuário de uma geração feita pela plataforma.
- Permitir uso sem IA externa: entrada manual e importação de análise estruturada.

### 11.3 Cobertura do diário

**RF-16 — Estado explícito do dia alimentar.** Cada dia deve ter pelo menos:

- **Sem registros:** nenhuma refeição confirmada; ingestão diária desconhecida.
- **Parcial:** existem refeições, mas o dia não foi declarado completo.
- **Declarado completo:** o usuário considera o diário representativo de tudo que consumiu.

A declaração de completude melhora a utilidade do cálculo, mas não elimina a incerteza das porções. Adicionar uma refeição ou corrigir o dia pode reabrir a revisão. Um jejum declarado é diferente de um dia vazio.

Cobertura do consumo e disponibilidade das estimativas são condições separadas. Um dia pode estar declarado completo e ainda ter uma refeição pendente de estimativa; nesse caso, seu total energético continua parcial.

Totais devem ser rotulados como **total registrado**, e só tratados como ingestão diária estimada quando a cobertura permitir. Alimentos consumidos durante treinos também entram no diário, com vínculo opcional à sessão, sem contagem repetida.

### 11.4 Ampliação — P1/P2

P1: foto de refeição ou rótulo, favoritos, receitas com rendimento e divisão por porções. P2: voz transcrita, códigos de barras, hidratação e integrações alimentares adicionais. Todos devem produzir registros corrigíveis no mesmo modelo; não podem criar totais paralelos incompatíveis.

## 12. Gasto energético e déficit calórico — P0

**RF-17 — Estimar gasto com origem e método.** A plataforma deve conseguir usar dados disponíveis para estimar gasto energético diário. O método concreto pode variar, mas precisa declarar qual fonte utiliza, quais componentes já estão incluídos e qual versão produziu o resultado.

Possíveis entradas: gasto total informado pelo wearable, componentes de repouso e atividade, atividades registradas, perfil e modelo estimativo. Nenhuma dessas fontes deve ser apresentada como medição perfeita do metabolismo.

Verificar também a cobertura temporal e de uso do dispositivo. Um total recebido para um dia com poucas horas de observação não deve parecer equivalente a um dia completo. Se um modelo preencher o período não observado, essa parcela precisa ser identificada como estimativa complementar.

### 12.1 Contabilidade sem duplicação

Há duas estratégias de cálculo possíveis:

1. **Total da fonte:** usar uma estimativa diária total confiável o suficiente para o contexto. Exercício já incluído nesse total não é acrescentado novamente.
2. **Composição de componentes:** usar componentes compatíveis e não sobrepostos. O método explica o que entra como repouso, atividade e outros componentes modelados.

O sistema não pode misturar as duas estratégias sem reconciliação explícita. Cada componente deve informar se é total, ativo, bruto ou líquido de repouso, conforme a semântica da origem. “Calorias do treino” e “calorias ativas do dia” podem se sobrepor.

Se duas fontes fornecem estimativas incompatíveis, selecionar um método canônico e guardar as alternativas como comparação. Não somar números só porque vieram de fontes diferentes.

### 12.2 Definições obrigatórias

**RF-18 — Balanço energético compreensível.**

Para um período com ingestão e gasto utilizáveis:

```text
balanço energético estimado = ingestão estimada − gasto total estimado
déficit estimado = gasto total estimado − ingestão estimada
```

Com essa convenção, déficit positivo indica ingestão inferior ao gasto; déficit negativo indica superávit. A interface deve preferir os rótulos “déficit” ou “superávit” para evitar ambiguidade de sinal.

São conceitos diferentes e devem aparecer separados:

| Conceito | Significado |
| --- | --- |
| Meta de ingestão | Quanto se pretende consumir conforme o plano vigente |
| Total registrado | Soma das refeições confirmadas até o momento |
| Margem para a meta | Meta de ingestão menos total registrado; não prova déficit real |
| Gasto acumulado | Estimativa disponível até o horário da consulta |
| Gasto diário projetado | Previsão para o fim do dia; depende de um método e pode mudar |
| Balanço do período | Comparação entre ingestão e gasto referentes ao mesmo intervalo |
| Déficit planejado | Intenção do plano vigente |
| Déficit retrospectivo estimado | Resultado calculado para um período com cobertura suficiente |

### 12.3 Regras do cálculo

- Sem alimentação completa o bastante, não afirmar déficit retrospectivo como se fosse conhecido.
- Sem gasto disponível, não inventar gasto zero.
- Um dia em andamento pode mostrar projeção, sempre identificada como projeção.
- Não comparar comida do dia inteiro com gasto de poucas horas sem explicitar o intervalo.
- Registrar método, fonte, horário, cobertura e versão de cada resultado.
- Recalcular quando mudarem refeições, gasto, perfil ou método.
- Mostrar totais semanais somente com sua cobertura; não tratar dias desconhecidos como déficit zero nem extrapolar dias incompletos silenciosamente.
- Diferenciar soma dos dias utilizáveis, média por dia utilizável e estimativa para toda a semana.
- Admitir que mesmo um diário completo e um relógio sincronizado ainda produzem uma estimativa.

### 12.4 Exemplo sintético de aceitação

Um wearable informa **2.800 kcal de gasto total diário**, incluindo **800 kcal de atividade**. O diário declarado completo contém **2.200 kcal**. O déficit estimado deve ser **600 kcal**. Acrescentar novamente as 800 kcal de atividade estaria errado.

Se o diário contém apenas o almoço e não foi declarado completo, a plataforma mostra o total registrado e a incompletude. Ela não apresenta as refeições ausentes como se tivessem zero calorias.

Esses valores são exemplos de contabilidade para validar o software, não metas alimentares.

## 13. Objetivos, metas e adaptação — P0

**RF-19 — Objetivos explícitos e versionados.** Permitir criar, alterar, concluir, pausar e arquivar objetivos. Registrar:

- Tipo, descrição e motivo.
- Prioridade em relação a outros objetivos.
- Ponto de partida e data da referência.
- Métrica ou critério de sucesso; pode ser quantitativo ou comportamental.
- Valor desejado, intervalo ou evento quando aplicável.
- Prazo desejado, opcional, sem garantia automática de viabilidade.
- Restrições e aspectos a preservar.
- Indicadores de acompanhamento e periodicidade de revisão.
- Estado e versões do plano associado.

Exemplos: reduzir gordura preservando massa magra e desempenho; manter peso; ganhar força; melhorar regularidade de sono; completar uma prova ou expedição; aumentar consistência nos registros.

Não é obrigatório que todo objetivo seja perder peso ou produzir déficit. O usuário pode ter um objetivo principal e objetivos secundários, com conflitos visíveis.

### 13.1 Plano e metas operacionais

**RF-20 — Plano coerente com o objetivo.** Traduzir o objetivo em referências acompanháveis: ingestão e macros quando aplicável, rotina, atividade, recuperação e frequência de registro. Distinguir metas informadas pelo usuário/profissional de sugestões calculadas ou geradas pela IA.

Criar um plano inicial utilizável sem exigir um plano importado. Quando faltarem dados essenciais para uma meta numérica, indicar o que falta e oferecer um plano provisório de acompanhamento/registro. Quando os dados necessários estiverem disponíveis, produzir as referências operacionais pelo método documentado, com hipóteses, vigência e revisão previstas.

Metas podem variar entre dias ou tipos de treino, desde que o método explique a variação e a relação com o período. Não aumentar ou reduzir automaticamente a ingestão apenas pela caloria isolada de um treino.

Um objetivo de composição corporal deve considerar os aspectos que a pessoa pediu para preservar. Preparar uma prova e reduzir gordura ao mesmo tempo exige explicitar a prioridade e o compromisso adotado.

### 13.2 Ciclo de adaptação

**RF-21 — Revisão baseada em evidência.** Em uma revisão manual ou periódica:

1. Reunir dados do período e a versão vigente do objetivo/plano.
2. Avaliar cobertura, atraso das fontes e consistência dos registros.
3. Comparar tendências com o ponto de partida e o período anterior.
4. Examinar adesão registrada, carga, sono, percepção e eventos relevantes.
5. Escolher entre manter, propor ajuste, pedir dados melhores ou suspender a adaptação automática por insuficiência de evidência.
6. Explicar a proposta, o que a sustenta, o que permanece incerto e o que ela pretende melhorar.
7. Registrar a decisão e acompanhar seus efeitos na revisão seguinte.

Revisão semanal é o padrão inicial proposto; janela de análise e frequência precisam ser configuráveis. Janelas mínimas, qualidade necessária, limiares e tamanho dos ajustes devem ser definidos, documentados e validados durante a implementação, sem números escondidos no comportamento.

### 13.3 Regras para não adaptar errado

- Um dia de peso ou uma refeição isolada não basta para mudar o plano.
- Registro alimentar incompleto não comprova baixa ingestão nem boa adesão.
- Mudanças de peso não devem ser atribuídas integralmente a gordura ou déficit.
- Uma projeção de progresso deve mostrar hipóteses; não garantir perda exata por uma conversão fixa de kcal em kg.
- Uma semana com dados insuficientes deve produzir uma revisão limitada, não uma recomendação numérica arbitrária.
- Não compensar automaticamente um excesso com restrição punitiva no dia seguinte.
- Considerar eventos, pausas, doença relatada e mudanças de rotina antes de interpretar uma tendência.
- Não reescrever metas passadas para parecer que o usuário sempre cumpriu o plano atual.
- Não concluir que aumento de carga ou déficit maior é sempre melhor.

### 13.4 Controle do usuário

**RF-22 — Propostas e decisões rastreáveis.** Por padrão, ajustes relevantes são propostos e aceitos ou rejeitados pelo usuário. Se existir um modo de adaptação automática, deve ser uma opção configurável, com limites claros, possibilidade de desativação e registro de cada mudança.

No modo automático solicitado para esta plataforma individual, o objetivo chama a IA local com peso datado, perfil suficiente, resumo das atividades e recuperação para definir calorias e proteína. Reavaliar diariamente e após mudanças relevantes; salvar uma versão com motivo e limitações. Mostrar na alimentação consumo/meta e quanto falta, preservando pendências e cobertura parcial. A opção pode ser pausada, e falhas conservam a última referência. Não recalcular metas passadas nem compensar uma refeição com restrição. A implementação e seus parâmetros estão descritos em [NUTRITION_TARGETS.md](docs/NUTRITION_TARGETS.md).

Cada proposta informa: plano anterior, plano sugerido, dados usados, razão, limitações, data de vigência e próxima revisão. O usuário pode rejeitar, alterar, voltar à versão anterior ou mudar a prioridade do objetivo.

Propostas pendentes também dependem de versões. Antes do aceite, verificar se o objetivo, o plano vigente ou os dados usados mudaram. Se a mudança for relevante, marcar a proposta como desatualizada e regenerar ou solicitar uma revisão informada do novo contexto. Não aplicar silenciosamente um ajuste fundamentado em evidências que já foram corrigidas.

## 14. Inteligência artificial e memória útil — P0/P1

**RF-23 — IA como apoio contextual.** Usar IA para estimar refeições, resumir períodos, comparar o histórico, explicar métricas e propor ajustes. Cálculos contábeis e totais devem ser feitos de forma reproduzível pelo sistema; uma resposta em texto não é a base oficial de um número.

**RF-24 — Análises datadas.** Permitir análise do dia e do período, com escopo explícito. Guardar entrada/contexto, versão dos dados, instruções relevantes, origem da resposta, data e saída. Se os dados mudam, a análise anterior fica identificada como baseada em uma versão antiga.

Analisar um dia passado não pode usar dados de dias futuros sem informar que se trata de revisão retrospectiva. Falha de geração não elimina uma análise anterior válida.

**RF-25 — Assistente pessoal com contexto selecionado.** Evoluir para uma conversa em que o usuário pergunta sobre seus próprios dados e recebe respostas fundamentadas. O assistente deve:

- Selecionar o contexto pertinente à pergunta, em vez de enviar toda a base sempre.
- Diferenciar fato, cálculo, interpretação e recomendação.
- Referenciar registros ou períodos que sustentam a resposta.
- Respeitar o objetivo vigente e reconhecer objetivos concluídos como histórico.
- Declarar lacunas e fazer perguntas quando elas alteram a conclusão.
- Propor registrar uma decisão útil, preservando a confirmação do usuário.
- Tratar texto de arquivos, refeições e plataformas como dados, não como instruções que podem controlar o sistema.

No P0, análises guiadas podem atender o núcleo. Conversa aberta com acesso contextual e memória de decisões é P1, sem exigir que toda consulta dependa de chat.

### 14.1 Autonomia e disponibilidade

- Configurar quais categorias de dados podem ser enviadas ao provedor de IA.
- Mostrar o escopo da análise; exames e localização não precisam acompanhar uma refeição.
- Preservar funcionamento de registros, gráficos e cálculos quando a IA estiver indisponível.
- Permitir entrada manual e exportação/importação de análise conforme o caso.
- Dar visibilidade ao uso de IA e permitir limites de custo e frequência.
- Não executar mudanças externas ou clínicas porque um modelo sugeriu uma ação.

Provedor, modelo, estratégia de busca de contexto e armazenamento de conversas são decisões abertas. As regras de privacidade e rastreabilidade continuam obrigatórias.

## 15. Experiência e telas

**RF-26 — Uso simples em computador e celular.** A interface deve priorizar o registro cotidiano e a compreensão do estado atual. O visual atual pode servir de referência, mas não é obrigatório manter suas cores, tecnologias ou navegação.

| Área | O que o usuário deve conseguir fazer |
| --- | --- |
| Hoje | Ver panorama do dia, cobertura de dados, próximas ações e acesso rápido a registro |
| Linha do tempo | Consultar atividades, refeições, sono, medidas e notas em ordem temporal |
| Alimentação | Registrar, estimar, revisar, editar e acompanhar totais/cobertura |
| Energia | Entender ingestão, gasto, projeção, déficit/superávit e método |
| Treinos | Consultar modalidades, sessões, força detalhada e evolução |
| Sono e recuperação | Ver histórico, check-ins e tendências com lacunas explícitas |
| Corpo | Registrar medidas e acompanhar evolução com datas e métodos |
| Saúde | Consultar documentos e referências pessoais dentro do escopo autorizado |
| Objetivos | Criar metas, ver progresso, revisar propostas e histórico de decisões |
| Análises/assistente | Gerar interpretações e consultar as evidências |
| Integrações | Conectar fontes, atualizar e resolver falhas ou duplicatas |
| Configurações e dados | Perfil, unidades, privacidade, backup, exportação e preferências |

Essas são áreas funcionais, não a obrigação de criar doze abas. A implementação pode reuni-las numa navegação menor.

### 15.1 Padrões de apresentação

- Mostrar unidade, período, referência temporal e origem perto de valores relevantes.
- Distinguir valor registrado, calculado, estimado e projetado.
- Usar estados vazios que indiquem como começar, sem sugerir comportamento que não ocorreu.
- Mostrar gráficos com lacunas, sem criar observações artificiais.
- Permitir abrir um indicador para entender seu cálculo e seus registros.
- Usar português brasileiro e unidades configuráveis; referência inicial em sistema métrico.
- Suportar teclado, legibilidade, contraste e rótulos claros.
- Sinalizar erros com contexto e ação possível, preservando trabalho já feito.

### 15.2 Lembretes — P1

Lembretes opcionais para registros ou revisões devem ser configuráveis. Alertar sobre alteração significativa, falha de sincronização ou necessidade de ação pode ser útil. Não gerar notificação repetitiva quando nada mudou e não usar mensagens de culpa por comida, corpo ou falta de registro.

## 16. Modelo conceitual de dados

**RF-27 — Dados estruturados e rastreáveis.** As entidades abaixo descrevem conceitos, não tabelas obrigatórias ou um esquema físico fechado.

| Entidade | Conteúdo e relações principais |
| --- | --- |
| Pessoa/perfil | Características, unidades, fuso e versões de informações relevantes |
| Preferência/restrição | Tipo, origem, vigência, contexto e confirmação |
| Conexão de fonte | Plataforma, permissões, cobertura e estado de sincronização |
| Observação de origem | Identificador externo, conteúdo recebido, datas e proveniência |
| Atividade canônica | Sessão real consolidada, modalidade e métricas selecionadas |
| Vínculo de origem | Relação entre atividade e registros Garmin/Hevy/Strava/arquivo |
| Exercício e série | Detalhes de força ligados à atividade/sessão |
| Registro de sono | Período observado, data da fonte, sinais e revisões |
| Medida corporal | Valor, unidade, método, data e origem |
| Check-in | Percepções subjetivas, escala, data e notas |
| Documento de saúde | Arquivo privado, categoria, data e referências extraídas |
| Observação de saúde | Valor/texto, unidade, origem, contexto e revisão |
| Refeição | Data/hora, tipo, descrição, confirmação e versões |
| Item alimentar | Alimento, porção, preparo, nutrientes, origem e incerteza |
| Estimativa de IA | Entrada, saída, hipóteses, modelo/origem e estado de revisão |
| Dia alimentar | Cobertura declarada e total dos registros confirmados |
| Estimativa de gasto | Intervalo, componentes, fonte, método e qualidade |
| Balanço energético | Ingestão/gasto usados, resultado, cobertura e versão do cálculo |
| Objetivo | Critério de sucesso, prioridade, prazo, estado e vigência |
| Plano/meta operacional | Referências aplicáveis ao período e versão vigente |
| Revisão/proposta | Evidências, comparação, justificativa e ajuste sugerido |
| Decisão | Aceite, rejeição ou edição, autoria, razão e vigência |
| Análise/conversa | Escopo, contexto, resposta, evidências e decisões relacionadas |
| Execução/importação | Trabalho, intervalo, estados, erros e itens processados |
| Relatório/exportação | Escopo, instante de referência, versão e arquivos gerados |

### 16.1 Metadados mínimos

Quando aplicável, guardar identificador estável, origem, data da observação, data de recebimento, fuso/intervalo, unidade, estado de qualidade, versão e referências aos dados usados. Manter distinto o que ocorreu ontem e o que foi importado hoje.

Para alterações, registrar valor anterior e novo, motivo e autoria: usuário, integração, cálculo ou IA. Correção humana não pode desaparecer quando o mesmo dado é importado novamente; a política de precedência deve ser explícita.

Datas devem distinguir horário do evento, dia local e convenção da origem. Viagens e mudança de fuso não podem duplicar um dia ou deslocar silenciosamente refeições e sono.

### 16.2 Camadas conceituais

1. **Originais:** arquivos e observações recebidos, preservados para auditoria e reprocessamento.
2. **Dados organizados:** registros canônicos, unidades normalizadas e vínculos entre fontes.
3. **Resultados derivados:** totais, tendências, carga, gasto e balanço com método versionado.
4. **Inteligência:** interpretações, sugestões, contexto e conversas.
5. **Decisões:** escolhas e planos efetivamente adotados pelo usuário.

Pode haver outra organização física, desde que preserve essas distinções. Recalcular não deve apagar originais nem tornar uma recomendação antiga indistinguível de uma decisão atual.

## 17. Privacidade, continuidade e portabilidade — P0

**RF-28 — Controle dos dados pessoais.** A base individual, documentos, imagens, rotas e credenciais são privados por padrão. A autenticação e os controles de acesso devem ser coerentes com o ambiente escolhido, incluindo o uso no celular.

- Credenciais ficam protegidas e fora do conteúdo mostrado ao usuário, da IA e dos logs comuns.
- Compartilhamento permite escolher categorias e período, com revisão do conteúdo.
- Exportações de treino não incluem exames ou alimentação sem indicação explícita.
- O usuário pode desconectar fontes, apagar dados específicos e solicitar exportação integral.
- Exclusões devem informar seu alcance sobre derivados, arquivos e retenção em backups.
- Dados privados não devem entrar em repositórios públicos, telemetria ou capturas de demonstração.

**RF-29 — Backup e recuperação verificáveis.** Preservar base, documentos, registros alimentares, análises, objetivos e decisões. A solução deve explicar o que cobre, quando foi verificada e como recuperar após perda do ambiente principal. Um arquivo existente ou volume persistente não é, sozinho, comprovação de recuperação.

**RF-30 — Exportação utilizável por outra aplicação ou IA.** Entregar formato estruturado documentado, metadados e anexos selecionados, além de um resumo humano do contexto atual.

O pacote de contexto deve permitir responder: quem é a pessoa no escopo autorizado, qual o objetivo vigente, quais restrições foram declaradas, que dados existem, qual a cobertura, quais métodos calculam as métricas e quais decisões foram tomadas.

Não exigir o mesmo provedor de IA ou a mesma infraestrutura para ler a exportação. A portabilidade deve incluir alimentação, decisões e análises, não somente atividades.

## 18. Requisitos não funcionais

| ID | Requisito | Resultado esperado |
| --- | --- | --- |
| RNF-01 | Integridade | Repetir importações ou operações não cria duplicatas; mudanças relacionadas ficam consistentes |
| RNF-02 | Resiliência | Falha de uma fonte ou IA preserva dados e funcionalidades independentes |
| RNF-03 | Reprodutibilidade | Mesmos dados, parâmetros e método produzem o mesmo cálculo |
| RNF-04 | Rastreabilidade | Todo resultado relevante aponta para sua origem, período e versão |
| RNF-05 | Privacidade | Dados pessoais têm acesso e compartilhamento controlados |
| RNF-06 | Usabilidade | Registro cotidiano funciona sem editar arquivos ou executar comandos |
| RNF-07 | Responsividade | Fluxos principais funcionam em telas de computador e celular |
| RNF-08 | Clareza | Ausência, parcialidade, projeção, falha e incerteza têm representações distintas |
| RNF-09 | Continuidade | Existe recuperação testável e migração documentada do histórico |
| RNF-10 | Desempenho | Consultar e registrar não depende da conclusão de uma importação longa ou de uma chamada de IA |
| RNF-11 | Custo | Chamadas de IA e operações caras são controláveis e não se repetem sem necessidade |
| RNF-12 | Evolução | Novas fontes e métodos entram sem destruir o modelo de histórico e proveniência |

Metas quantitativas de latência, volume e disponibilidade devem ser declaradas na proposta técnica, de acordo com o ambiente escolhido. O dimensionamento inicial é individual, com anos de histórico e crescimento contínuo; não exige infraestrutura de uma plataforma de milhões de usuários.

## 19. Critérios de aceitação do núcleo

Os cenários abaixo constituem um conjunto mínimo de validação de produto. Devem ser exercitados com dados sintéticos; não exigem usar dados reais de saúde em testes ou demonstrações.

| Cenário | Comportamento esperado | Requisitos |
| --- | --- | --- |
| A01 — Usuário novo | Consegue criar perfil, importar/conectar uma fonte e criar um objetivo sem intervenção técnica | RF-01, 04, 19 |
| A02 — Histórico incompleto | A aplicação mostra áreas vazias e cobertura; não inventa repouso, comida ou sono | RF-05, 07, 10, 16 |
| A03 — Importação repetida | Importar duas vezes o mesmo conteúdo não altera contagens nem totais por duplicação | RF-05, 27 |
| A04 — Sessão Garmin + Hevy | Há uma sessão real, com detalhes das duas fontes, sem duplicar duração/energia/carga | RF-06, 07, 17 |
| A05 — Correspondência ambígua | Duas atividades parecidas permanecem distinguíveis e podem ser revisadas/desvinculadas | RF-06 |
| A06 — Falha de uma fonte | Histórico preservado, fonte com erro visível e estado parcial; outra fonte pode atualizar | RF-05 |
| A07 — Sono parcialmente corrigido | Campo vazio novo não apaga duração histórica válida; correção real é rastreável | RF-05, 10, 27 |
| A08 — Refeição com IA | Descrição vira itens revisáveis; só a versão salva entra no total | RF-14, 15 |
| A09 — Porção desconhecida | Hipótese aparece ou pergunta é feita; não há falsa certeza de quantidade | RF-15 |
| A10 — Correção alimentar | Editar a refeição atualiza total e balanço, preserva rastreabilidade e não duplica entrada | RF-14, 18, 27 |
| A11 — Repetição de salvamento | Repetir o envio da mesma operação não cria uma segunda refeição | RF-14 |
| A12 — Diário parcial | Total registrado aparece; déficit retrospectivo não é tratado como conhecido | RF-16, 18 |
| A13 — Nenhuma refeição | Ingestão desconhecida; não há suposição automática de zero ou jejum | RF-16, 18 |
| A14 — Gasto com exercício incluído | No exemplo 2.800 − 2.200, déficit é 600; atividade não é somada novamente | RF-17, 18 |
| A15 — Gasto indisponível | Pode existir meta e total alimentar, mas o déficit recebe estado indisponível/limitado | RF-17, 18 |
| A16 — Dia em andamento | Gasto acumulado e projeção final têm rótulos/intervalos distintos | RF-18 |
| A17 — Semana com lacunas | Cobertura aparece; dias desconhecidos não entram como zeros nem como observações reais | RF-18, 21 |
| A18 — Medida antiga | Mostra data/método; não apresenta composição corporal antiga como atual | RF-11 |
| A19 — Objetivos concorrentes | Prioridade e aspectos a preservar influenciam a proposta de plano | RF-19, 20 |
| A20 — Um dia fora da curva | Não ocorre ajuste relevante apenas por uma observação isolada | RF-21 |
| A21 — Revisão sem evidência | Sistema mantém ou limita a revisão e pede dados úteis; não inventa novo alvo | RF-21 |
| A22 — Ajuste aceito/rejeitado | Versões e motivos são preservados; rejeitar não muda o plano vigente | RF-22 |
| A23 — Meta concluída | Deixa de orientar a recomendação atual, mantendo seu histórico | RF-03, 19, 25 |
| A24 — IA indisponível | Refeições manuais, consulta e cálculo continuam; resposta anterior permanece preservada | RF-15, 23, 24 |
| A25 — Resposta inválida da IA | Conteúdo inválido é rejeitado e não contamina números oficiais | RF-15, 23 |
| A26 — Análise histórica | Usa contexto até o período selecionado ou declara revisão retrospectiva | RF-24 |
| A27 — Dado alterado após análise | Resultado antigo é marcado como baseado em dados anteriores; novo cálculo é possível | RF-24, 27 |
| A28 — Escopo de privacidade | Estimar alimento não envia automaticamente exames ou rotas ao provedor | RF-23, 28 |
| A29 — Exportação integral | Outra aplicação consegue ler dados, unidades, objetivos, decisões e cobertura | RF-30 |
| A30 — Recuperação | Ambiente separado recupera registros e anexos do backup com verificação de integridade | RF-29 |
| A31 — Virada de dia/fuso | Horários e convenções não duplicam sessões nem deslocam silenciosamente o diário | RF-10, 27 |
| A32 — Uso no celular | Registrar refeição, consultar o dia e revisar proposta funcionam sem comandos técnicos | RF-26 |
| A33 — Refeição pendente | Texto pode ser salvo sem IA; total e déficit indicam estimativa pendente, sem contar a refeição como zero | RF-14, 16, 18 |
| A34 — Wearable com cobertura parcial | Gasto mostra cobertura limitada e eventual complemento modelado; não aparenta observação completa | RF-17, 18 |
| A35 — Plano inicial sem importação | Perfil e objetivo com dados suficientes produzem um plano utilizável, versionado e com revisão prevista | RF-19, 20 |
| A36 — Adaptação efetiva | Em dados sintéticos com cobertura suficiente e tendência que exige ajuste pela política escolhida, há proposta fundamentada; aceite muda o plano a partir da vigência e a revisão seguinte avalia o efeito | RF-20, 21, 22 |
| A37 — Proposta com contexto alterado | Correção ou nova importação relevante antes do aceite marca a proposta antiga e exige revalidação; o plano não muda por um aceite desinformado | RF-22, 27 |
| A38 — Instalação vazia | O núcleo e seus testes funcionam sem arquivos privados do projeto anterior; migração só é exigida quando uma base é fornecida | RF-01, 04, 19, 20 |
| A39 — Dia completo com calorias pendentes | Aparece subtotal conhecido e estimativa pendente; declaração de completude não transforma esse subtotal em ingestão total utilizável | RF-15, 16, 18 |

## 20. Ordem de construção sugerida

As fases organizam a implementação. Não representam prazos ou um cronograma já acordado.

### Fase 0 — Definir contratos e preparar a migração

Inventariar fontes e formatos e, quando houver, dados existentes; definir entidades, semântica de datas/unidades, proveniência e métodos escolhidos. Preparar dados sintéticos e regras de importação. Definir ambiente inicial e acesso pelo celular. Preservar o histórico fornecido antes de substituir qualquer sistema.

### Fase 1 — Construir a memória confiável

Entregar perfil, armazenamento, uma primeira integração de wearable, Hevy, importação nos formatos P0, atividades canônicas, sono, medidas e consulta de referências de saúde. Migrar histórico e acervo quando fornecidos. Entregar estados de sincronização, correções, backup e exportação desde o início.

**Saída:** dados reais podem entrar e ser consultados sem duplicação nem perda silenciosa.

### Fase 2 — Fechar o ciclo alimentar e energético

Entregar texto/manual, estimativa com IA, revisão, edição, cobertura diária, gasto com semântica explícita e balanço por dia/período. Refeições durante treino devem integrar o mesmo total alimentar.

**Saída:** o usuário entende o total registrado e o déficit/superávit estimado quando há cobertura suficiente.

### Fase 3 — Objetivos e adaptação

Entregar objetivos editáveis, plano vigente, progresso, revisão de tendências, proposta de ajuste e histórico de decisões. Integrar análise guiada de alimentação, energia, treino e recuperação.

**Saída:** o produto cumpre o pedido completo de definir um objetivo e adaptar a orientação.

### Fase 4 — Aprofundar a experiência

Entregar fotos, conversa contextual, receitas/favoritos, entrada e extração revisada de documentos, planejamento e lembretes conforme necessidade. Ampliar conectores somente depois de garantir o ciclo central.

**Saída:** mais conveniência e profundidade sem criar registros ou cálculos incompatíveis.

O núcleo só está completo ao final da Fase 3, com os requisitos P0 e seus critérios de aceitação. Um painel com gráficos ou um chat isolado não conclui o produto.

## 21. Decisões que permanecem abertas

| Decisão | Liberdade da implementação | Condição obrigatória |
| --- | --- | --- |
| Linguagem e frameworks | Escolher conforme equipe e ambiente | Entregar comportamentos verificáveis e manutenção viável |
| Banco e arquivos | Relacional, documentos ou combinação | Integridade, histórico, consulta e portabilidade |
| Ambiente | Local, servidor privado ou hospedagem adequada | Privacidade, continuidade e acesso seguro no uso previsto |
| Interface | Web responsiva, aplicativo ou combinação | Fluxos principais confortáveis no celular |
| Provedor/modelo de IA | Um ou mais provedores, modelo local ou combinação | Escopo controlado, validação, rastreabilidade e funcionamento sem IA |
| Integrações | APIs, mecanismos autorizados, arquivos e sincronizadores | Cobertura real verificada, credenciais protegidas e falhas explícitas |
| Gasto energético | Wearable, modelo próprio ou composição | Sem sobreposição, com método/fonte/intervalo documentados |
| Carga e recuperação | Reutilizar ou revisar o modelo atual | Explicar modalidade, entrada, unidade, fórmula e limitações |
| Adaptação | Regras determinísticas, modelos, IA ou combinação | Evidência suficiente, limites documentados e decisões versionadas |
| Base nutricional | Bases estruturadas, rótulos, manual e IA | Origem, porção e incerteza distinguíveis |
| Agendamento | Serviço interno ou infraestrutura externa | Estado persistente e transparência de falhas |
| Visual e nome | Definir identidade nova ou reutilizar AscentIQ | Clareza, legibilidade e coerência de uso |

Antes de implementar, a IA deve propor as decisões necessárias e justificar os compromissos. Não precisa copiar Python, React, PostgreSQL, Docker ou o formato de relatórios atual. Também não deve deixar decisões essenciais de semântica indefinidas dentro de código aparentemente pronto.

## 22. Fora do escopo inicial

- Plataforma social, rankings ou feed público.
- Sistema para clínicas, múltiplos pacientes ou gestão de profissionais.
- Diagnóstico automatizado, ajuste de medicação ou substituição de acompanhamento clínico.
- Garantia de calorias exatas, gasto exato ou resultado corporal em prazo fechado.
- Suporte imediato a todos os fabricantes de relógio.
- Escrita automática em plataformas externas, compras ou alteração de inscrições/eventos.
- Preservação obrigatória da arquitetura, do design ou dos algoritmos atuais.

Esses limites não impedem expansão posterior. Mantêm a primeira entrega concentrada na plataforma individual solicitada.

## 23. Instrução de passagem para outra IA

Você vai construir uma plataforma individual de saúde e fitness a partir desta SPEC. Considere o documento autossuficiente para entender o produto; o código existente é referência opcional e os dados pessoais são material privado de migração.

Sua tarefa é:

1. Identificar os requisitos P0 e organizar a implementação pelo ciclo completo do usuário.
2. Escolher arquitetura e métodos, registrando as decisões e suas limitações.
3. Modelar originais, registros canônicos, cálculos, interpretações e decisões como conceitos distinguíveis.
4. Entregar importação/sincronização, histórico, alimentação com IA, balanço energético e objetivos adaptativos.
5. Preservar correções, proveniência, cobertura, privacidade e exportação.
6. Validar os cenários de aceitação com dados sintéticos e verificar a recuperação.
7. Documentar o que funciona, o que é parcial e quais integrações ainda não estão disponíveis.
8. Quando uma base anterior for fornecida, migrar a história pessoal com conferência de equivalência, sem sobrescrevê-la antes da validação. Uma instalação vazia deve funcionar sem esse material.

Não invente dados para completar telas. Não use respostas de IA como fonte única de totais matemáticos. Não chame uma semana sem registros de semana de descanso ou de déficit. Não conclua o trabalho após criar apenas o dashboard: a entrega deve permitir **coletar dados, registrar alimentação, entender energia, definir um objetivo e revisar a orientação com base no progresso**.

## 24. Referências locais para auditar o ponto de partida

Esta seção ajuda quem também tiver acesso ao projeto atual. Não é necessária para compreender os requisitos futuros. Os caminhos são relativos à pasta que contém esta SPEC.

| Referência | O que fundamenta |
| --- | --- |
| `athlete-agent/README.md` | Origem esportiva, importadores, memória e métricas |
| `athlete-agent/dashboard/README.md` | Portal, alimentação, análise diária, sono, relatórios e operação |
| `athlete-agent/docs/DATABASE.md` | Modelo versionado, banco, migração, backup e recuperação |
| `athlete-agent/docs/METRICS.md` | Definições do modelo atual de carga e métricas de montanha |
| `athlete-agent/docs/PRIVACY.md` | Separação de dados privados e código público |
| `athlete-agent/dashboard/nutrition.py` | Estimativa alimentar, validação e persistência do diário |
| `athlete-agent/dashboard/web/src/Nutrition.jsx` | Fluxo atual de registrar, revisar, salvar e excluir refeições |
| `athlete-agent/dashboard/daily_analysis.py` | Contexto diário, sono, análise e resposta importada |
| `athlete-agent/dashboard/snapshot.py` | Consolidação e apresentação do contexto existente |
| `athlete-agent/dashboard/repository.py` | Persistência, revisões e projeções estruturadas |
| `athlete-agent/dashboard/jobs.py` | Estados de execução, fila e agendamento |
| `athlete-agent/scripts/` | Importadores, parsers e reconstrução de métricas |
| `athlete-agent/prompts/system_prompt.txt` | Evolução das prioridades e interpretação contextual do atleta |

Documentos antigos podem mencionar objetivos já concluídos. Na migração, resolver a vigência a partir de registros revisados e da prioridade atual; não transformar uma preferência histórica em regra universal da nova plataforma.
