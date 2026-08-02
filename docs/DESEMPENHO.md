# Desempenho — o que foi medido e por quê

Todos os números são desta máquina (RTX 5050 8 GB, Ryzen). Os scripts estão em
`tests/` e podem ser rodados de novo a qualquer momento.

## Tempo de cada etapa (medido em `tests/bench_pipeline.py`)

Contado a partir do instante em que você **começa** a falar. A frase de teste
dura 3,1s, então tudo que aparece antes disso acontece **enquanto você ainda fala**.

### Comando da casa ("Jarvis, liga a luz da sala")

| etapa | quando |
|---|---|
| reator acende | **0,48s** |
| primeira parcial na tela | 0,48s |
| transcrição final | 3,26s |
| luz acionada + resposta falada | **3,26s** |

Você termina de falar em 3,12s → **0,14s depois a ação já aconteceu**.
Não passa por LLM nenhum: o Intent Router resolve e a resposta ("Claro.") já
está pré-gerada em disco.

### Pergunta que vai pro LLM ("Jarvis, quem foi Santos Dumont?")

| etapa | quando | custo da etapa |
|---|---|---|
| reator acende | 0,48s | — |
| transcrição final | 3,0s | 2,5s (você falando) |
| primeira palavra do LLM | 3,4s | **0,35s** |
| primeiro áudio da resposta | 6,5s | 3,1s (síntese de voz) |
| resposta inteira falada | 29–37s | depende do tamanho da resposta |

O "Um momento." toca **na hora** (3,5s), então não há silêncio constrangedor.

## Decisões tomadas com base em medição

### Transcrição: um modelo só, o `small`

Testado com 8 frases reais x 3 condições de áudio (limpo / com ruído /
"microfone do outro lado da sala"), sempre com o nome no meio:

| modelo | reconhece a chamada | erro no comando (difícil) | s/frase |
|---|---|---|---|
| **whisper small + prompt** | **8/8** | 0,242 | **0,12s** |
| whisper medium + prompt | 8/8 | 0,108 | 8,23s |
| whisper large-v3-turbo | 5/8 | 0,505 | **14,73s** |
| nemotron 3.5 streaming | 2/8 | 0,573 | 0,10s |
| canary-1b-v2 | 3/8 | 1,038 | 1,90s |
| distil-large-v3 | 1/8 | 1,029 | 10,05s |

Dois achados que mudaram o desenho:

1. **O `large-v3-turbo` não roda bem nesta placa.** 14,7s por frase na GPU e
   4,7s na CPU — o CTranslate2 não tem kernel otimizado pra esta arquitetura.
   Ele estava no caminho crítico e ninguém tinha medido.
2. **O `initial_prompt` é o que faz o modelo conhecer "Jarvis".** Sem ele o
   nome sai como "Já Luiz", "Jairus", "Já vi" — e o assistente te ignora.
   Custa quase nada no `small` (0,12s contra 0,14s).

Por isso **não vale manter dois modelos**: o `small` é tão rápido quanto o
modelo "rápido" (0,12s x 0,10s) e reconhece o nome muito melhor (8/8 x 2/8).
Ele mesmo gera as parciais (re-transcreve o trecho a cada 0,45s), que é o que
acende o reator em 0,48s. Um modelo, menos VRAM, menos coisa pra dar errado.

O modo `hibrido` (Nemotron + Whisper) continua no código, é só trocar
`stt.engine` no `settings.yml`.

### LLM: local, com dois cuidados

`ollama_chat/qwen3.5:0.8b`. Duas coisas descobertas medindo:

- **`think` precisa ser desligado.** O Qwen3.x gasta a resposta inteira
  "pensando" e devolve texto **vazio**: 3,39s e nada. Com `think=False`: 0,29s
  e responde. O `/no_think` no texto do prompt **não** resolve.
- **Prompt gordo custa caro em modelo pequeno.** Com histórico longo a primeira
  palavra levava 2,4s; enxugando (2 trocas, truncadas) e com a GPU desperta,
  0,35s.

Comparação (`tests/bench_llm.py`), primeira palavra:

| modelo | 1ª palavra | qualidade |
|---|---|---|
| qwen3.5:0.8b (local) | **0,26s** | fraca — erra fatos |
| deepseek-chat (nuvem) | 0,96s | boa |

Trocar é uma linha no `settings.yml`.

### A GPU dormindo custava 2 segundos

A placa cai para 225 MHz (P8) quando fica parada, e a primeira inferência paga
o "acordar": **2,61s parado x 0,80s desperta**. `keep_alive` do Ollama não
resolve — o modelo continua carregado, é a GPU mesmo.

Solução: quando você chama "Jarvis", o servidor dispara um pedido mínimo ao LLM
e ao serviço de voz **em paralelo** (`agents.agent.despertar_gpu`). A GPU acorda
enquanto você ainda está falando o comando, e quando a resposta chega a placa já
está no clock cheio. Custo: uma geração de 1 token.

## O que ainda pesa

O **tempo total da resposta falada** (29–37s) é dominado pela síntese de voz:
a voz clonada gera a ~1,2x o tempo real e a resposta do modelo às vezes sai
longa. Não atrapalha a sensação de rapidez (o áudio começa em 6,5s e vai
saindo em pedaços), mas se quiser cortar isso pela metade, o caminho é limitar
o tamanho da resposta do modelo.

## Como repetir os testes

```
python tests/bench_pipeline.py 3        # tempo de cada etapa (servidor no ar)
python tests/bench_stt.py               # compara modelos de transcrição
python tests/bench_whisper_tamanhos.py  # qualidade x tempo por tamanho
python tests/bench_llm.py               # LLM configurado
python tests/diag_gpu_ociosa.py         # prova o efeito da GPU dormindo
python tests/diag_whisper_gpu.py        # o modelo está mesmo na GPU?
```

Rode com o servidor parado quando o teste carrega modelos — GPU disputada
distorce tudo (o `large-v3-turbo` chegou a marcar 0,28s numa medição suja e
14,7s numa limpa).
