# IA local com Ollama

A alimentação, o assistente e as análises podem usar Ollama sem chave OpenAI e sem cobrança por chamada de API. O modelo roda no computador; usa processamento, memória, armazenamento e energia locais. As calorias continuam sendo estimativas que precisam de revisão.

## Instalar

Com Docker em execução, inicie o serviço e baixe o modelo multimodal:

```powershell
docker compose --profile local-ai up -d ollama
docker compose --profile local-ai exec ollama ollama pull qwen3.5:4b
```

Para NVIDIA, use o arquivo adicional desde a inicialização:

```powershell
docker compose -f compose.yaml -f compose.ollama-gpu.yaml --profile local-ai up -d ollama
docker compose -f compose.yaml -f compose.ollama-gpu.yaml --profile local-ai exec ollama ollama pull qwen3.5:4b
docker compose --profile local-ai exec ollama ollama ps
```

O Compose mantém os modelos no volume `ollama_models`. Não remova os volumes ao atualizar. O serviço não publica portas no host; somente a API da aplicação o acessa pela rede Docker. O container usa `OLLAMA_NO_CLOUD=1`, e a aplicação rejeita modelos identificados como cloud e URLs de provedores externos nesse modo. A documentação oficial descreve [Docker](https://docs.ollama.com/docker), [execução local e nuvem desativada](https://docs.ollama.com/faq) e [o modelo Qwen 3.5 4B](https://ollama.com/library/qwen3.5:4b).

## Configurar e usar

No painel, abra Dados e fontes → Inteligência artificial → Configurar/Alterar conexão. Selecione **Ollama local**, informe `qwen3.5:4b` como modelo e salve. Não é necessário preencher uma chave. O provedor selecionado vale para alimentação, assistente e extração documental com IA; não existe fallback automático para OpenAI quando o Ollama falha.

Também há suporte às variáveis `ASCENTIQ_AI_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3.5:4b` e `OLLAMA_BASE_URL=http://ollama:11434`. A configuração salva no painel tem prioridade ao iniciar a API. Uma chave OpenAI previamente guardada permanece cifrada, mas não é usada pelo modo local.

Na alimentação, descreva quantidades/preparo ou anexe uma foto e clique em Salvar refeição. A refeição fica gravada primeiro; a IA calcula e salva os nutrientes automaticamente, atualizando os totais. Não há botão separado de análise, entrada manual de calorias nem confirmação adicional da estimativa. Para corrigir ou tentar novamente uma estimativa pendente, edite a descrição e salve; a foto já registrada é reutilizada. Os itens, as hipóteses, a origem e o modelo ficam disponíveis para consulta.

O status da alimentação é atualizado quando a aba volta ao foco ou a conexão muda em outra aba, sem apagar o rascunho. Falhas preservam os dados e não contam calorias desconhecidas como zero. O primeiro pedido pode levar mais tempo por carregar o modelo; os pedidos seguintes mantêm-no aquecido por cinco minutos. O prazo da API local é de 180 segundos, com proxy de 210 segundos.

## Conferir

```powershell
docker compose --profile local-ai exec ollama ollama list
docker compose --profile local-ai exec ollama ollama ps
docker compose --profile local-ai logs --tail 30 ollama
docker compose --profile maintenance run --rm db-tools test
```

`ollama list` confirma o download. `ollama ps` confirma CPU/GPU durante uma inferência. As análises registram `source=ollama` e o modelo. Os testes usam dados sintéticos e verificam seleção sem chave, persistência, fotos, contrato JSON, falhas sem fallback pago, estimativa automática ao salvar, tentativas repetidas sem duplicação e preservação de edições concorrentes. Não publicar prompts, documentos nem logs pessoais.
