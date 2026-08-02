# Agentes, registro e observador

Como o JARVIS decide o que fazer com o que você falou, o que ele guarda de cada
interação e como isso vira melhoria depois.

## O caminho de uma frase

```text
"Jarvis, liga a luz da sala"
        │
        ├─ 1. Intent Router (regex, ~0ms) ──► casou? Skill executa. FIM.
        │
        ├─ 2. Roteador (qwen3.5:0.8b, ~0,35s)
        │      ├─ papo social ──► ele mesmo responde
        │      └─ resto ──────► escolhe UM agente
        │
        └─ 3. Agente escolhido (ADK) ──► ferramentas ──► resposta falada
                    │
                    └─ Registro: áudio + transcrição + rota + resposta
                            │
                            └─ Observador (só se deu sinal de problema)
```

Cada camada é mais cara que a anterior, então a de cima resolve o máximo que
consegue. Medido: **6 de 14** frases de teste nem chegam ao LLM.

## Os agentes

Definidos em `config/settings.yml` → `agentes.lista`. O prompt e as ferramentas
de cada um ficam em `server/jarvis/agents/especialistas.py`.

| Agente | Cuida de | Ferramentas | Modelo |
|---|---|---|---|
| `casa` | luzes, temperatura, dispositivos | controlar luz, temperatura, MCPs | local |
| `sistema` | o computador e o próprio assistente | — | local |
| `conversa` | perguntas gerais, papo | — | local |
| `avancado` | pedidos difíceis, vários passos | — | **nuvem** (GPT-5.6 Luna) |

### Adicionar um agente

1. Uma entrada em `agentes.lista` (nome, `descricao`, `exemplos`);
2. o prompt dele em `PROMPTS` e as ferramentas em `FERRAMENTAS`
   (`especialistas.py`).

Os `exemplos` não são enfeite: são o que mais move a agulha no roteador. Com só
dois exemplos por agente, "que temperatura está aqui" ia parar no `sistema`; com
três, foi pro `casa`. Use frases do jeito que você fala de verdade.

### Ligar/desligar a nuvem

```yaml
nuvem:
  ativo: true                    # false = 100% local, nada sai da máquina
  modelo: openai/gpt-5.6-luna
  api_key_env: OPENAI_API_KEY    # a chave fica em config/.env
  reasoning_effort: low          # o mínimo que este modelo aceita
```

Com `ativo: false` — **ou sem a chave no ambiente** — o agente `avancado`
desaparece da lista sozinho e o roteador nem sabe que ele existia. Oferecer o
agente sem a chave faria toda pergunta difícil morrer em erro de autenticação e
voltar como "não entendi".

### Velocidade da nuvem

A resposta é falada em voz alta: cada segundo "pensando" é silêncio pra quem
está esperando. Medido A/B **intercalado** (a API oscila muito; medir tudo de A
e depois tudo de B faz a oscilação virar "diferença" — isso me enganou na
primeira medição, que sugeriu um ganho 3x maior do que o real):

| | 1ª palavra |
|---|---|
| pelo agente, `low` | **0,93–1,08s** |
| pelo agente, `high` | 1,24–1,78s |
| chamada crua, `low` | 0,62–0,87s |

`low` é o mínimo aceito — `minimal` e `none` são recusados por este modelo. Sem
o parâmetro ele já se comporta perto do `low`, mas deixar explícito trava o
comportamento rápido em vez de depender do padrão da API. O caminho do agente
(ADK + prompt do JARVIS) custa outros ~0,2–0,3s.

**A primeira chamada do dia era o problema de verdade**: DNS + TLS + cliente do
litellm custavam **5,57s** contra 0,69s nas seguintes — e isso caía justo na
pergunta difícil, quando a pessoa mais espera. O `aquecer()` do start agora abre
a conexão com o provedor também (`nuvem pronta (aquecida)` no log). No servidor
real, a primeira pergunta pra nuvem depois de reiniciar caiu pra **1,74s**.

Detalhe que custou uma tentativa: aquecer com `max_tokens=1` **não funciona** com
modelo de raciocínio — ele pensa antes de escrever e estoura o limite
("Could not finish the message"), perdendo o aquecimento em silêncio.

## Por que o roteador quase não responde sozinho

Ele é um modelo de 0.8b. Solto, inventa:

- perguntado "aumenta o volume", respondeu com uma explicação falsa sobre o
  áudio da casa em vez de mandar pro agente do sistema;
- respondendo "bom dia", chegou a falar em voz alta o próprio molde do prompt
  (`<uma frase curta>`).

Por isso a resposta direta dele passa por duas travas **no servidor**, não na
boa vontade do modelo:

1. `pode_responder_direto()` — só aceita se a frase for cumprimento ou
   agradecimento. Qualquer coisa com fato, estado ou ação vai obrigatoriamente
   pra um agente;
2. filtro de lixo — resposta com `<>`, `{}` ou vazia é descartada.

E cumprimento nem chega até ele: virou intent local (`social.greeting`) com
áudio pronto, que sai em ~0ms e ainda acompanha a hora do dia.

Quando a decisão vem inaproveitável, o servidor escolhe o agente contando
palavras em comum com a descrição e os exemplos (`palpite_por_palavras`) — sem
LLM, instantâneo. O JARVIS **nunca** fica sem destino.

## Registro: o que fica guardado

Cada interação vira uma linha na tabela `registros` e um WAV em
`server/data/gravacoes/<data>/<hora>_<sessão>.wav`:

- o áudio do que você falou (com o pre-roll, então o começo da frase não falta);
- a transcrição, a rota escolhida (com confiança e motivo), o agente, a resposta;
- os tempos de cada etapa.

```yaml
registro:
  ativo: true
  guardar_dias: 30      # gravações mais velhas somem sozinhas no start
```

Para ver:

```bash
python tests/ver_registros.py 10
```

Serve pra três coisas: descobrir onde ele erra **com a sua voz** (e não com
áudio sintético de teste), alimentar o observador, e virar material de treino do
modelo pequeno mais pra frente.

## Observador

Um modelo mais esperto (a nuvem, quando ligada) relendo o que deu errado. Roda
**depois** da resposta, em segundo plano — nunca atrasa o JARVIS.

Só entra quando há sinal de problema:

```yaml
observador:
  ativo: true
  quando: [roteador_incerto, pedido_repetido, tarefa_falhou]
```

| Gatilho | Quando dispara |
|---|---|
| `roteador_incerto` | a rota saiu com confiança baixa |
| `pedido_repetido` | você pediu a mesma coisa de novo em até 2 min (sinal de que não funcionou) |
| `tarefa_falhou` | deu erro na execução |

Ele devolve, e o servidor grava no registro: o agente que **devia** ter sido
escolhido, a transcrição correta e uma frase explicando. Exemplo real do teste:

> `[roteador_incerto]` Devia ter ido para casa, pois é um comando para apagar a
> luz do quarto. — agente correto: `casa`

### Uma armadilha que já custou caro

A checagem de `pedido_repetido` roda **depois** de gravar o registro. Sem
ignorar o próprio id, a interação se compara com ela mesma e **tudo** vira
"repetido" — no primeiro teste com voz real, 5 de 5 interações acionaram o
observador. Daí o parâmetro `ignorar_id` em `store.pedido_repetido`.

## Eco do prompt do Whisper

O Whisper recebe um `initial_prompt` ("Falando com o Jarvis.") pra não escrever
"Já Luiz" no lugar do nome. Em silêncio, ele **repete esse prompt** como se
fosse fala — às vezes truncado e em loop ("falando com falando com o jarvis f").
Como tem "Jarvis" dentro, isso passava pelo wake word e virava um pedido
fantasma, que chegou a acionar um agente de verdade.

`WhisperStt._eco()` derruba isso: é eco quando nenhuma palavra é nova (toda
palavra é do prompt ou um pedaço de uma) e o prompt inteiro está presente.
"Jarvis" sozinho e "Falando com o Jarvis sobre energia solar" passam normalmente
(`tests/test_eco_prompt.py`).

## Testes

| Arquivo | O que cobre | Precisa de |
|---|---|---|
| `tests/test_roteador.py` | a decisão nunca trava nem inventa agente | nada |
| `tests/test_intents.py` | intents locais, inclusive cumprimentos | nada |
| `tests/test_eco_prompt.py` | eco do prompt do Whisper | nada |
| `tests/test_observador.py` | gatilhos + análise de verdade | chave da nuvem |
| `tests/bench_roteador.py` | velocidade e acerto das duas camadas | Ollama |
| `tests/test_agente_nuvem.py` | cada agente responde (inclusive a nuvem) | Ollama + chave |
| `tests/bench_nuvem_onde_vai_o_tempo.py` | `low` vs `high`, e o custo do ADK | chave |
| `tests/bench_nuvem_primeira_chamada.py` | quanto custa a 1ª chamada fria | chave |
| `tests/bench_nuvem_no_servidor.py` | a 1ª pergunta difícil no servidor real | servidor no ar |
| `tests/test_fim_da_fala.py` | toda resposta falada termina com `speak_end` | nada |
| `tests/test_agentes_e2e.py` | voz real ponta a ponta + registro no disco | servidor no ar |
| `tests/test_janela_destrava.py` | a janela do PC não fica presa depois de falar | app com `--remote-debugging-port=9333` |
| `tests/ver_registros.py` | ver o que ficou guardado | nada |

## Duas coisas que quebram fácil

**`speak_end` é obrigatório.** O device liga o "estou falando" no `speak` de
seq 0 e só desliga no `speak_end`. Um caminho novo que fale sem mandar o fim
deixa a janela do PC presa na tela, opaca, até a interação seguinte — foi o que
acontecia com toda resposta pronta da biblioteca. Use `_fim_da_fala()`, nunca
mande o evento na mão.

**Nada de trabalho pesado antes do `set_idle()`.** Enquanto o `on_final` não
retorna, o pipeline fica em `BUSY` e o microfone está surdo. Gravar o WAV e
commitar no SQLite ali dentro deixava o JARVIS sem ouvir por um tempo depois de
cada resposta. Capture o que precisa na hora e jogue o resto pra
`asyncio.create_task`.
