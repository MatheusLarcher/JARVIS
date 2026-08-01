# Voz do JARVIS (clonada)

A voz é clonada por referência a partir de uma amostra de áudio, usando **Chatterbox
multilíngue** rodando na GPU local. Uso doméstico/pessoal deste assistente.

## Peças

| Onde | O quê |
|---|---|
| `server/data/voice/jarvis_ref.wav` | amostra de referência (mono 24 kHz, ~11 s) — **fora do git**, fica só na máquina; se sumir, rode o `prepare_voice_ref.py` de novo com o áudio original |
| `server/voice_service/service.py` | serviço HTTP na **porta 8041** (env `jarvis-tts`) |
| `server/jarvis/tts/engine.py` | engine `clone` (chama o serviço) + `edge` (reserva) |
| `server/jarvis/tts/warmer.py` | pré-gera frases previsíveis (hora, temperatura) |
| `config/settings.yml → tts.voice_profiles` | perfis `jarvis_br` (clone) e `jarvis_edge` |

Ambientes separados de propósito: o Chatterbox pina `torch==2.6` e o servidor precisa de
`torch cu128` (RTX 5050 = sm_120). O env `jarvis-tts` tem torch cu128 instalado por cima do
pin — o aviso do pip é esperado e a geração funciona.

## Trocar a voz por outra amostra

```
python server/scripts/prepare_voice_ref.py <audio_de_referencia>
python server/scripts/build_library.py --force --verify     # regera a biblioteca
```

`prepare_voice_ref.py` acha os trechos de fala (Silero VAD), junta os vizinhos, corta o
melhor bloco (8–15 s), normaliza e salva a referência. Quanto mais limpa a amostra (sem
música/efeitos), melhor a clonagem.

## Por que `--verify`

A voz clonada às vezes engasga em frases muito curtas ("Sim?"). Com `--verify` o script
gera várias tomadas, transcreve cada uma com o **próprio STT do JARVIS** e fica com a que
o reconhecedor entende melhor (WER 0 = perfeita). Sem isso, o áudio pode sair arrastado.

Conferir a biblioteca a qualquer momento:

```
python server/scripts/check_library.py        # transcreve tudo e mostra o WER
```

Medir se a voz gerada parece a referência (env `jarvis-tts`):

```
python server/voice_service/validate_voice.py <arquivo.wav> [outro.wav ...]
```

Similaridade de locutor (cosseno) — referência ~1.0, voz clonada ~0.6–0.8, voz genérica ~0.45.
**Importante:** instanciar `VoiceEncoder()` direto dá pesos aleatórios e similaridade falsa
de 1.000; o script usa o encoder treinado que vem dentro do modelo (`model.ve`).

## Latência

Gerar a voz clonada é mais lento que o tempo real (RTF ~1,7–2,5 com o modelo já
aquecido). Quatro coisas escondem isso:

1. **biblioteca pré-gerada** cobre as respostas de comando → instantâneo;
2. **cache por hash** (`server/data/tts_cache`) reaproveita qualquer frase repetida
   (pergunta repetida = resposta imediata);
3. **aquecedor de cache** (`tts/warmer.py`) mantém sempre pronta a frase da hora atual, do
   minuto seguinte e da temperatura — perguntar as horas responde na hora;
4. **fala em streaming** (abaixo) — a mais importante para respostas do LLM.

Se o serviço de voz estiver fora, o perfil cai automaticamente pro `jarvis_edge`
(edge-tts) pra nunca ficar mudo.

## Falar enquanto o LLM ainda escreve

Esperar a resposta inteira antes de gerar o áudio custava **até 40 s de silêncio**.
Agora o texto do LLM é consumido em stream e cortado em pedaços faláveis
(`tts/chunker.py`): o primeiro sai com ~3 palavras (a voz começa logo) e os
seguintes crescem até 14 (prosódia melhor, menos chamadas). Cada pedaço vira áudio
e o dispositivo toca **em fila, na ordem** (`speak` com `seq`, `speak_end` no fim).

Além disso, ao cair no LLM o JARVIS solta na hora um "Um momento." pré-gerado —
o primeiro token do modelo demora ~6 s e isso tira a sensação de travado.

Medido (pergunta inédita, resposta de 40 palavras):

| | antes | agora |
|---|---|---|
| começa a falar | ~40 s | **~0 s** (aviso) / ~6 s (resposta) |
| termina | ~40 s | ~40 s |

Ajustes em `config/settings.yml → tts`: `stream_primeiras_palavras` (3) e
`stream_max_palavras` (14). Teste: `python tests/test_tts_stream.py "pergunta"`.

Como o RTF é maior que 1, respostas longas saem em blocos com pequenas pausas —
por isso o agente é instruído a responder em no máximo 2 frases curtas.

## Subir o serviço

`server\start_jarvis.bat` já abre os dois (voz + servidor), cada um com watchdog próprio.
Sozinho: `server\start_voice.bat`. Saúde: `GET http://127.0.0.1:8041/health`.
Log: `server/data/voice.log`.
