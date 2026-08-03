# Roadmap — o que ainda não existe

O que já existe está em [REFERENCIA.md](REFERENCIA.md). Aqui é o que falta,
organizado por **quem destrava**: o que depende de uma informação ou de um
aparelho seu, e o que é só trabalho de código.

Cada item diz o **porquê**, para não virar lista de desejos sem contexto.

---

## Depende de você

### 1. Conectar a casa de verdade — o maior buraco

Hoje `home_assistant.mode: mock`: as luzes que ele "acende" são simuladas.
Nenhuma lâmpada acende de verdade. Era um dos pilares do projeto.

**Falta:** URL do seu Home Assistant, um token de acesso longo, e os
`entity_id` reais das lâmpadas e do sensor de temperatura.

**Depois disso:** `mode: real` em `settings.yml`, `HA_TOKEN` no `.env`, os ids
em `house.yml`, e habilitar o MCP em `mcp.yml` se quiser que o agente descubra
dispositivos sozinho.

### 2. Instalar nos aparelhos

Os APKs existem (`releases/Jarvis.apk`, `releases/Jarvis-Watch.apk`) e foram
validados **em emulador** — o do relógio nem isso. Nunca rodaram em hardware
real.

Cada aparelho precisa do IP do notebook, do `device_id` e do token
(`config/devices.yml`).

**Risco conhecido:** o cache do "Sim?" no Android é guardado por nome de
arquivo, então trocar a voz não chega no aparelho. A correção é usar a URL
inteira na chave do cache — não corrigi porque não dá pra validar sem o
aparelho na mão.

### 3. Usar de verdade por alguns dias

Todos os testes ponta a ponta usam **voz sintética**. O wake nunca foi
calibrado com a sua voz num cômodo real, e o log já registrou um
`chamou: 'Jarvis'` **sem ninguém falar**.

Usar alguns dias resolve duas coisas de uma vez: eu calibro
(`fuzzy_max_edits`, `vad.min_speech_ms`) com dados seus, e o registro junta o
material para o item 6.

### 4. Trocar a senha do keystore

A senha antiga ficou no histórico do git. Como o APK não foi publicado em loja
nenhuma, gerar um keystore novo é indolor. Ver [SEGURANCA.md](SEGURANCA.md).

### 5. ~~Decidir sobre a voz clonada no repositório~~ — resolvido em 02/08/2026

A voz do JARVIS (`jarvis_ref.wav`) sobe, porque é o que permite regerar a
biblioteca. O áudio de uso — o assistente respondendo e as gravações dos seus
pedidos — não sobe, e foi apagado do histórico. Ver
[SEGURANCA.md](SEGURANCA.md).

---

## É comigo

### 6. Ensinar o modelo a te entender (LoRA no roteador)

O registro já guarda áudio + transcrição + rota escolhida + a correção do
observador — é exatamente o material de treino. Falta **volume de uso real**.

Com dados suficientes, um LoRA no `qwen3.5:0.8b` melhora a rota com o seu jeito
de falar. O mesmo material serve para um fine-tune de transcrição, que é o
único caminho para o Parakeet (ver [STT.md](STT.md)).

### 7. Ferramentas de verdade para o agente `sistema`

Hoje ele só sabe dizer que não sabe: não abre programa, não mexe no volume, não
lê o que está na tela. É o agente mais fácil de tornar útil, porque tudo roda na
mesma máquina.

### 8. Resposta melhor

O `qwen3.5:0.8b` é fraco — perguntado sobre Santos Dumont, ele fala de "um
santo". Foi escolha consciente (velocidade primeiro). Caminhos: subir para um
modelo local maior, mandar mais coisa para a nuvem, ou o LoRA do item 6.

### 9. Tela para ouvir e corrigir os registros

Hoje só `python tests/ver_registros.py` no terminal. Uma tela onde você ouve o
áudio, corrige a transcrição e a rota transformaria o uso diário em dado de
treino — e fecharia o ciclo do item 6.

### 10. Acesso externo (Cloudflare Tunnel)

Para o assistente funcionar fora de casa. **Antes disso** é obrigatório
revisar segurança: hoje não há TLS (é LAN), nem rate limit, nem rotação
automática de token. Ver [SEGURANCA.md](SEGURANCA.md).

### 11. Wake word própria em PT-BR

O `hey_jarvis` do openWakeWord foi treinado com pronúncia inglesa: com voz
brasileira o score fica em ~0,03. Hoje quem segura a peteca é a transcrição.
Treinar um modelo com "Jarvis" em português daria um atalho instantâneo de
verdade.

### 12. Contexto de lugar mais fino

Hoje o lugar sai da rede Wi-Fi + configuração manual do cômodo. Com
GPS/Bluetooth/geofence ele saberia em que cômodo você está sem você dizer —
o que faz "liga a luz" acertar sozinho.

### 13. Streaming nativo do Nemotron

O `att_context_size` do cache-aware streaming baixaria a latência das parciais.
Só vale a pena se voltarmos ao modo híbrido.

### 14. GIF de demonstração no README

Mostrar funcionando vale mais que descrever.

---

## Decisões que já foram tomadas (e por quê)

Para não refazer discussão:

| Assunto | Decisão | Motivo |
|---|---|---|
| Transcrição | Whisper `small`, um modelo só | Tão rápido quanto o "rápido" e muito melhor no nome (8/8 x 2/8). |
| Parakeet TDT | Testado e descartado por ora | Velocidade empatada e sem como aprender o nome sem treino. |
| Gemma 4 E2B (áudio direto) | Descartado | Em 4-bit fica surdo; em bf16 não cabe em 8 GB. |
| `large-v3-turbo` | Descartado nesta placa | 14,7 s por frase — faltam kernels no CTranslate2 para a arquitetura. |
| Nuvem | Opcional, `reasoning_effort: low` | O "pensar" vira silêncio para quem espera a voz. |
| Resposta direta do roteador | Só papo social, travado no servidor | Modelo de 0.8b inventa fato com naturalidade. |
| Cumprimento | Regra local com áudio pronto | Sai em ~0 ms e não passa por LLM nenhum. |
