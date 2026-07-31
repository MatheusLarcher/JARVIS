# JARVIS

Assistente pessoal de voz estilo Homem de Ferro: fale **"Hey Jarvis"** perto do tablet
(ou toque no reator no celular/relógio), peça **"liga a luz da sala"** e a casa obedece —
tudo processado no seu notebook, sem mandar áudio pra internet.

## Como ligar

O servidor liga sozinho com o Windows (tarefa "JARVIS Server"). Pra ligar na mão:

```
server\start_jarvis.bat
```

Depois abra `http://SEU-IP:8040` em qualquer navegador da casa — essa é a tela do PC.

## Instalar nos aparelhos

| Aparelho | Arquivo | Como |
|---|---|---|
| Tablet / Celular | `releases\Jarvis.apk` | Copie pro aparelho e instale. Na primeira tela, informe o IP do notebook (ex.: `192.168.0.10:8040`), o device id (`tablet-sala` ou `celular-matheus`) e o token que está em `config\devices.yml`. |
| Galaxy Watch | `releases\Jarvis-Watch.apk` | Instale via ADB por Wi-Fi no relógio. Device id `galaxy-watch`. |

No tablet, deixe o app aberto no suporte: a tela fica preta com relógio, temperatura e o
reator respirando. É só falar "Hey Jarvis".

## O que dá pra pedir hoje

- "liga / desliga a luz" (da sala, do quarto, do escritório — ou do cômodo onde você está)
- "que horas são?"
- "qual a temperatura?"
- Qualquer outra pergunta vai pra IA e volta falada.

No celular e no relógio também dá pra **tocar no reator** pra falar sem wake word.

## Configurar a casa de verdade

Por enquanto as luzes rodam em modo simulado. Pra conectar no Home Assistant real,
edite `config\settings.yml` (`home_assistant: mode: real` + url) e coloque o token em
`config\.env` (`HA_TOKEN=...`). Os cômodos e lâmpadas ficam em `config\house.yml`.

## Documentação técnica

Está em [`docs/`](docs/): arquitetura, APIs, como adicionar skills, dispositivos,
trocar STT/TTS/LLM e a memória do projeto.
