# Reconhecimento de fala (STT)

## O que está em uso

`config/settings.yml → stt.engine: hibrido` — dois modelos, cada um no que faz melhor:

| Papel | Modelo | Por quê |
|---|---|---|
| Transcrições **parciais** | `nvidia/nemotron-3.5-asr-streaming-0.6b` | rápido; é o que reconhece "Jarvis" e acende o reator ainda no meio da frase |
| Transcrição **final** (vira comando) | `faster-whisper large-v3-turbo` | acerta o comando mesmo com ruído/eco |

Trocar: `stt.engine` aceita `hibrido`, `nemotron`, `whisper` ou `dummy`.

## Por que assim (medição, não achismo)

`python tests/bench_stt.py` gera frases em vozes diferentes, cria uma versão "sala real"
(volume baixo + eco + filtro) e mede WER e tempo. Resultado nesta máquina (RTX 5050):

| motor | WER limpo | WER com ruído | s/frase |
|---|---|---|---|
| whisper large-v3-turbo | **0.000** | **0.000** | 0,70 |
| nemotron 3.5 streaming | 0.016 | 0.062 | 0,47 |
| parakeet-tdt-0.6b-v3 | 0.135 | 0.146 | 1,73 |

O Whisper acerta tudo, mas não é streaming (precisa da fala inteira) — daí o híbrido.

Latência medida no fluxo real: reator acende **~570 ms** depois de você começar a falar;
comando executado ~2,3 s após terminar a frase.

> Atenção ao rodar o benchmark: se a GPU estiver ocupada, o Whisper cai para CPU e o
> tempo salta para ~45 s por frase (foi o que aconteceu na primeira medição). Rode com
> os serviços parados.

## Armadilhas conhecidas

- **Carregar os dois modelos em paralelo quebra**: ambos importam `transformers` e o
  import do Python estoura com `cannot import name 'AutoModel'`. Em `stt/hibrido.py` o
  carregamento é sequencial de propósito.
- **NeMo exige `transformers` da série 4.x.** Com 5.x o import falha.
- **O modelo NeMo não é thread-safe**: duas transcrições ao mesmo tempo devolvem string
  vazia, sem erro. Há um `threading.Lock` em cada engine.
- Os três modelos (Nemotron + Whisper + voz clonada) somam ~7 GB de VRAM numa placa de
  8 GB. Quando disputam a GPU, as parciais atrasam (medi 9,8 s em vez de 0,6 s). Se ficar
  ruim, use `stt.engine: whisper` (abre mão das parciais) ou `nemotron`.

## Diagnóstico

```
curl http://127.0.0.1:8040/api/audio/debug     # o áudio está chegando? o VAD acusa fala?
python tests/diag_microfones.py                # qual microfone escuta a sala
python tests/test_mic_real.py                  # fluxo completo pelo microfone de verdade
```
