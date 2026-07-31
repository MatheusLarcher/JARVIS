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

Geração é lenta (RTF ~4: 2,5 s de fala levam ~10 s). Por isso:

1. **biblioteca pré-gerada** cobre as respostas de comando → instantâneo;
2. **cache por hash** (`server/data/tts_cache`) reaproveita qualquer frase repetida;
3. **aquecedor de cache** (`tts/warmer.py`) mantém sempre pronta a frase da hora atual, do
   minuto seguinte e da temperatura — perguntar as horas responde na hora.

Só frase inédita (resposta do LLM) paga a geração. Se o serviço de voz estiver fora, o
perfil cai automaticamente pro `jarvis_edge` (edge-tts) pra nunca ficar mudo.

## Subir o serviço

`server\start_jarvis.bat` já abre os dois (voz + servidor), cada um com watchdog próprio.
Sozinho: `server\start_voice.bat`. Saúde: `GET http://127.0.0.1:8041/health`.
Log: `server/data/voice.log`.
