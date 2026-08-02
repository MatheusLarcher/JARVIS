# Reconhecimento de fala (STT)

## O que está em uso

`config/settings.yml → stt.engine: whisper` — **um modelo só**, o `small` com
`initial_prompt`. Ele faz as duas coisas: gera as parciais (re-transcrevendo o
trecho em andamento a cada 0,45s, que é o que acende o reator cedo) e a
transcrição final que vira comando.

Trocar: `stt.engine` aceita `whisper`, `hibrido` (Nemotron nas parciais +
Whisper na final), `nemotron` ou `dummy`.

## Por que um modelo só (medição, não achismo)

`python tests/bench_stt.py` gera 8 frases com o nome no meio, em 3 vozes, e cria
três condições: limpa, com ruído e "microfone do outro lado da sala". Mede o que
importa: **reconhece a chamada?** e **acerta o comando?**

| motor | reconhece a chamada (difícil) | erro no comando (difícil) | s/frase |
|---|---|---|---|
| **whisper small + prompt** | **8/8** | 0,242 | **0,12** |
| whisper medium + prompt | 8/8 | 0,108 | 8,23 |
| whisper large-v3-turbo | 5/8 | 0,505 | 14,73 |
| nemotron 3.5 streaming | 2/8 | 0,573 | 0,10 |
| canary-1b-v2 | 3/8 | 1,038 | 1,90 |
| distil-large-v3 | 1/8 | 1,029 | 10,05 |

Dois motivos para não manter dois modelos:

1. O `small` é **tão rápido quanto** o modelo "rápido" (0,12s x 0,10s) e reconhece
   o nome muito melhor (8/8 x 2/8). Um modelo a menos = menos VRAM e menos
   coisa para dar errado.
2. O `large-v3-turbo`, que era a peça de qualidade, **não roda bem nesta placa**:
   14,7s por frase na GPU (4,7s na CPU!). Faltam kernels otimizados no
   CTranslate2 para esta arquitetura. Confirmado em `tests/diag_whisper_gpu.py`.

Latência no fluxo real: reator acende **0,48s** depois de você começar a falar;
comando executado **0,14s** depois de terminar a frase.

> Atenção ao medir: com a GPU disputada os números mentem feio — o mesmo
> large-v3-turbo marcou 0,28s numa medição suja e 14,7s numa limpa. Pare os
> serviços antes de rodar benchmark de modelo.

## O nome "Jarvis" precisa ser ensinado ao modelo

Sem `initial_prompt`, o STT escreve o nome como "Já Luiz", "Jairus", "Já vi" —
e o assistente simplesmente te ignora. Com o prompt, 8/8 no áudio difícil contra
0/8 sem ele. No `small` isso não custa tempo (0,12s x 0,14s); no turbo custava
segundos.

Configurável em `settings.yml → stt.initial_prompt` e `stt.hotwords`
(o padrão é montado com o nome + os cômodos de `house.yml`).

Como rede de segurança, o reconhecedor (`audio/wakeword.py`) ainda aceita o nome
mal transcrito **quando vem seguido de um comando conhecido** — assim
"Já, Luiz. Acende a luz da sala" funciona, mas a TV falando "já vi esse filme"
não acorda o assistente.

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
