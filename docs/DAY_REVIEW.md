# Análise do dia: alimentação, treino e recuperação

O botão **Analisar meu dia** aparece em Hoje e Alimentação. Uma consulta monta o prompt com os registros datados e o horário local, chama o Ollama e salva a resposta e o contexto no histórico do assistente. O campo opcional permite informar fome, jantar concluído, pouca energia no treino ou algo que ainda não foi registrado. Copiar o prompt e consultar os dados usados continuam disponíveis após a geração.

O contexto salvo inclui perfil, peso datado, objetivo, meta e sua origem, refeições e nutrientes, cobertura alimentar, gasto e sua cobertura, atividades e força consolidadas, sono/carga/check-ins dos últimos sete dias e planejamento do dia. Os dados exatos e o prompt usado são consultáveis separadamente. Para interpretar, o modelo local recebe comparações calculadas (abaixo da meta, referência atingida ou desconhecida), modalidades, cobertura, relato e planejamento, sem precisar refazer a aritmética. Horário de cadastro de comida não é tratado como horário comprovado da refeição. Rótulos sem registros não são refeições obrigatórias ou prova de omissão. Planejamento não vira execução, e treino vinculado à força não entra duas vezes na contagem de sessões.

O horário pertence à consulta, no fuso do perfil. Para uma data passada, a análise assume modo histórico e não aplica a hora de agora àquele dia. Datas futuras são rejeitadas. O prompt exclui fotos, documentos médicos e geometria; prefere apenas os dados necessários ao pedido.

## Interpretação de energia

A diferença entre ingestão registrada e meta não é déficit energético. O software só fornece o déficit estimado quando o gasto e a alimentação são utilizáveis e o subtotal corresponde ao mesmo diário completo. Registro vazio ou desconhecido permanece desconhecido; jejum depende de declaração explícita.

Uma heurística pede revisão quando, após 18h no dia atual, o registro está abaixo de 70% da meta. Outra sinaliza déficit estimado maior que 15% do gasto quando há cobertura utilizável. São parâmetros do produto para chamar atenção aos registros, sem diagnóstico, limiar clínico ou prova de baixa disponibilidade energética. O modelo recebe esse limite de interpretação explicitamente.

A resposta explica hipóteses e opções para agora e para o próximo treino. O prompt orienta a não celebrar restrição excessiva, ordenar completar todo o saldo à noite, prescrever treino para compensar comida, deduzir descanso de registros ausentes ou ajustar automaticamente a meta. Fadiga isolada não deve ser atribuída com certeza à alimentação. Falta de fome, peso antigo, estimativa de porções e fator de atividade inferido entram nas limitações. Orientações dependem do relato, recuperação e planejamento disponíveis; recorrência pode justificar avaliação profissional.

Os fatos numéricos são apresentados por código: subtotal conhecido, nutrientes, meta, diferença aritmética, cobertura, sessões, sono e referência de peso. Refeições no diário já representam registros de consumo; a origem da estimativa não torna um jantar futuro nem exige cadastrá-lo outra vez. A referência de gasto total modelado não é chamada de metabolismo basal. A IA retorna três seções em JSON com interpretação qualitativa; estrutura inválida ou algarismos no texto da IA impedem salvar uma nova resposta. Essa validação e a preparação de comparações reduzem aritmética livre e formatos incompletos, mas não certificam a correção clínica ou factual de toda interpretação do modelo. Índices Fitness/Fatigue/Form e valores de carga/duração não entram no prompt de interpretação como limiares de recuperação. Check-ins pessoais em escala de zero a dez viram categorias baixa (até três), intermediária (até seis) e alta, sem significado diagnóstico.

O [consenso do COI sobre REDs (2023)](https://bjsm.bmj.com/content/57/17/1073) fundamenta a cautela com exposição problemática à baixa disponibilidade energética e efeitos sobre saúde/desempenho; um dia isolado não estabelece diagnóstico. O [NIDDK](https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner) descreve planejamento individual de calorias e atividade. Essas referências não validam a heurística ou a meta individual da aplicação. Os parâmetros da meta diária estão em [NUTRITION_TARGETS.md](NUTRITION_TARGETS.md).

## Histórico, custo e falhas

A análise usa exclusivamente Ollama local e não recorre a API paga, mesmo se a seleção de provedor mudar durante a consulta. Compartilha o limite diário de análises salvas do assistente (20 por padrão). O mesmo contexto, relato, modelo e minuto de consulta reutiliza a resposta; horário ou registros novos permitem uma nova leitura. A resposta mostra quando foi feita, preserva o prompt e não altera perfil, diário, plano ou treinos.

Registros alterados deixam a resposta identificada como anterior, com convite para gerar novamente. Falha do modelo mantém as respostas anteriores. Relatos da análise não viram check-ins ou medidas sem um cadastro explícito separado.

Os testes usam dados fictícios e verificam horário atual/histórico, desconhecido versus zero, diário parcial, refeições não obrigatórias e já consumidas, consolidação, privacidade, planejamento, mudança de registros, concorrência de leituras, cache, autenticação/CSRF, falhas, estrutura da resposta, rejeição de aritmética da IA e bloqueio de provedor pago.
