# Metas alimentares diárias com IA local

Com um objetivo ativo e perfil suficiente, o Ollama define a referência diária de calorias e proteína. A alimentação mostra **registrado / meta**, barras de progresso e quanto falta para calorias, proteína, carboidratos e gorduras. O saldo usa somente o que foi registrado; um diário parcial não comprova ingestão total, e nutrientes pendentes tornam o saldo provisório.

## Atualização e controle

A opção **Objetivos → Meta alimentar automática** vem ativada nesta implementação e pode ser pausada. Salvar perfil, peso, objetivo, preferências ou check-in acorda o cálculo em segundo plano. Importações e sincronizações são percebidas na consulta periódica, a cada minuto. O dia novo também inicia uma revisão. A interface consulta a meta a cada 15 segundos sem apagar o rascunho da refeição. O tempo total depende da inferência e dos recursos locais.

O contexto igual no mesmo dia reutiliza a versão persistida, inclusive após reinício. Falhas têm intervalo mínimo de cinco minutos antes de uma nova tentativa do mesmo contexto. A última meta continua disponível quando o Ollama falha, retorna valores inválidos ou quando falta algum dado. Um contexto alterado durante a inferência impede a publicação daquele resultado.

Cada publicação cria uma versão datada do plano, com modelo, contexto, justificativa, limitações e referência de gasto. O sistema preserva metas históricas e planos de vigência futura. A geração automática só publica para o dia atual. Para manter um plano manual ou profissional sem substituição pela IA, pause a atualização automática.

## Dados usados

- Perfil com idade ou nascimento, altura, parâmetro de sexo exigido pelo cálculo metabólico e último peso datado. O software não deduz esse parâmetro pelo nome. Uma referência de gasto declarada pode substituir a equação, mas o peso continua necessário para proteína.
- Objetivo principal e demais objetivos ativos, respeitando prioridade e vigência.
- Atividades dos últimos 14 dias: modalidade, duração, distância e elevação; volume dos últimos sete dias como referência de atividade.
- Check-ins dos últimos três dias para recuperação. Doença declarada, dor ou fadiga de oito ou mais bloqueiam a sugestão de déficit nessa geração.
- Treinos do dia separados do histórico e medidas de peso dos últimos 30 dias, sem registros futuros. A vigência do objetivo não é interpretada como data de prova; proximidade de evento exige data explícita.

Não entram refeições, fotos, documentos médicos ou geometria GPX. O cálculo não compensa uma refeição com restrição posterior. Peso com mais de 30 dias aparece nas limitações, sem virar uma medida atual inventada.

## Método e parâmetros do produto

O software calcula a referência de repouso pela equação já documentada em [PLATFORM.md](PLATFORM.md), ou usa o gasto declarado. Multiplica o repouso pelo fator de atividade informado; na ausência dele, usa uma **heurística do produto**, baseada nos minutos de treino dos últimos sete dias:

| Minutos registrados | Fator estimado |
| --- | --- |
| Menos de 90 | 1,40 |
| 90 a menos de 240 | 1,55 |
| 240 a menos de 420 | 1,70 |
| 420 ou mais | 1,85 |

Essa aproximação não mede rotina, metabolismo ou atividade fora dos treinos. O total já inclui atividade habitual: calorias isoladas de treino e totais parciais do relógio não são somados novamente.

O Ollama recebe essa referência e escolhe o ajuste energético, a proteína por quilograma e a fração energética de gordura, explicando a decisão. A aplicação valida valores finitos, restringe o ajuste a no máximo 15% abaixo (ou ao limite menor configurado) e 10% acima da referência, respeita o piso configurado e o repouso estimado, e arredonda calorias em passos de 50 sem ultrapassar esses limites. Proteína fica entre 1,4 e 2,0 g/kg; o prompt prioriza 1,8–2,0 para perda de gordura com preservação muscular, permitindo exceções justificadas. Gorduras podem ocupar 25–30% da energia, uma faixa conservadora do produto. Carboidratos completam a energia restante. O prompt considera a demanda dos treinos do dia ao distribuir os macros, sem prometer uma necessidade medida ou ajuste clínico. Resultado incompatível é rejeitado e preserva o plano anterior.

A versão `daily_local_ai_targets_v2` entra no contexto e na identificação do cálculo, provocando uma revisão dos planos antigos mesmo sem mudança de perfil. O histórico é preservado. A explicação deve distinguir estimativa de gasto de manutenção comprovada, reconhecer peso antigo e rotina desconhecida e não usar uma data de vigência como evidência de evento futuro. O histórico de peso oferece contexto; não há calibração automática de gasto por ingestão e tendência nesta geração.

As limitações publicadas são construídas pela aplicação a partir dos dados verificados: método do gasto, idade do peso, disponibilidade de medidas e check-ins, prazo explícito e distribuição estimada dos macros. A lista livre produzida pelo modelo não é tratada como evidência de ausência de exames, sintomas ou medições na vida da pessoa. Algumas afirmações fisiológicas não verificadas também bloqueiam a publicação da justificativa.

A [posição da ISSN sobre proteína e exercício](https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/) descreve a faixa de 1,4–2,0 g/kg para a maioria dos indivíduos saudáveis que se exercitam. O [Body Weight Planner do NIDDK](https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner) ilustra planejamento individual com peso, atividade e objetivo. Essas fontes não validam a heurística de atividade, os limites de ajuste ou a distribuição de macros desta aplicação. A referência calculada permanece uma estimativa, sem promessa de adequação clínica ou resultado garantido.

## Execução e validação

As metas automáticas usam exclusivamente o Ollama local configurado. Não existe fallback para uma API paga; escolher OpenAI deixa esse recurso indisponível até selecionar Ollama. Consulte [OLLAMA.md](OLLAMA.md) para instalação.

Os testes usam perfis e atividades fictícios e verificam contexto mínimo, calorias/macros persistidos, reutilização, mudança de dia/peso, histórico, planos futuros, falta de dados, pausa, ausência de fallback pago, recuperação, respostas inválidas e alterações concorrentes. A validação de interface e de inferência real também usa dados descartáveis.
