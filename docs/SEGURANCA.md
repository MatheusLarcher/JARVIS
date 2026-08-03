# Segurança e privacidade

O que **não** pode entrar no repositório, o que foi encontrado numa auditoria
antes de abrir o projeto, e o que fazer se algo vazar.

## O que nunca vai pro git

| O quê | Onde fica | Por quê |
|---|---|---|
| Chaves de API (OpenAI, DeepSeek, Home Assistant) | `config/.env` | acesso pago/privado em nome seu |
| Tokens dos aparelhos | `config/devices.yml` | quem tem o token fala com o seu assistente |
| Gravações das suas falas | `server/data/gravacoes/` | áudio seu, dentro de casa |
| O JARVIS respondendo | `server/data/library/`, `tts_cache/` | áudio de uso do dia a dia |
| Keystore de assinatura do Android | `apps/android/*.keystore` + senha | permite assinar updates no seu nome |
| Banco e cache | `server/data/jarvis.db`, `tts_cache/` | contém o que você falou |

Todos estão no `.gitignore`. Os modelos versionados são
`config/devices.example.yml` e o `.env.example` — copie e preencha.

## Auditoria de 02/08/2026 (antes de tornar o repo público)

O repositório ainda **não tinha remote**, então nada havia sido publicado.

### Achados

**1. Tokens dos aparelhos versionados — corrigido.**
`config/devices.yml` com os 5 tokens reais estava no git, e o token do `web-dev`
aparecia escrito na mão em 8 arquivos de teste e como fallback no `App.jsx`.
O servidor escuta em `0.0.0.0:8040`, então qualquer um na mesma rede já poderia
usar; com o Cloudflare Tunnel do roadmap, viraria credencial exposta na internet.

Feito: arquivo fora do git (`devices.example.yml` como modelo), testes lendo o
token de `tests/conexao.py`, fallback removido do `App.jsx` e **tokens
rotacionados** — os antigos, que ficaram no histórico, não valem mais nada.

**2. Senha do keystore de release nos docs — corrigido.**
A senha estava escrita por extenso em `INSTALACAO.md` e `MEMORIA.md`. O arquivo
`.keystore` nunca foi versionado, mas senha publicada + qualquer vazamento
futuro do arquivo = alguém assina um update se passando pelo app.
Feito: senha removida dos docs (o valor antigo continua no histórico, por isso
a pendência abaixo).

> **Pendente com você:** trocar a senha do keystore (ou gerar um novo). Como o
> APK ainda não foi publicado em loja nenhuma, gerar outro é indolor.

**3. Áudio de uso versionado — resolvido, com reescrita de histórico.**
`server/data/library/` tinha 34 WAV do JARVIS respondendo ("Pronto.",
"Bom dia."…). Decisão: **a voz do JARVIS sobe, o áudio de uso não.**

- **Sobe:** `server/data/voice/jarvis_ref.wav` — é a referência do clone. Com
  ela, quem clonar o repositório regera a biblioteca na mesma voz.
- **Não sobe:** a biblioteca, o cache do TTS e as gravações dos seus pedidos.

Tirar do tracking **não bastava**: os 34 arquivos estavam em 5 commits do
histórico e voltariam com qualquer clone. Como o repositório ainda não tinha
remote, o histórico foi reescrito com
`git filter-repo --path server/data/library --invert-paths`. Resultado: 0
ocorrências em qualquer commit, `.git` de 20,6 MB → 2,2 MB, e os arquivos
intactos no disco (o assistente não perdeu a voz — validado depois).

Quem clonar recupera o áudio pronto com:

```
python server/scripts/build_library.py
```

Sem isso ele continua falando, só que sintetizando na hora
(`library.texto_qualquer`).

### Sem problema

- `config/.env` **nunca** esteve no histórico do git.
- `.keystore`, `server/data/voice/` e as gravações nunca foram versionados.
- Nenhum padrão de chave de API (`sk-`, `ghp_`, `AIza`, chave privada) no
  conteúdo versionado.
- Nome, empresa (`com.larchertech.jarvis`) e nomes de rede (`wifi-home`,
  `wifi-2d`) aparecem em config e ids — informação pessoal leve, não é
  credencial. Se incomodar, dá pra renomear.

## Se um token vazar

Apagar o arquivo **não resolve**: o valor antigo continua no histórico. Troque:

```bash
python server/scripts/trocar_tokens.py            # mostra o que faria
python server/scripts/trocar_tokens.py --aplicar  # troca de verdade
```

Ele gera tokens novos, faz backup do `devices.yml` e **atualiza a cópia que o
app da bandeja guarda** em `%APPDATA%\jarvis-desktop\config.json` — sem isso o
PC fica tentando entrar com o token velho e o servidor recusa (4401).

Depois: reinicie o servidor e o app; nos celulares e no relógio, informe o
token novo na tela de configuração.

## Postura de segurança do projeto (o que existe hoje)

- Autenticação por token por aparelho, obrigatória no WebSocket e no REST.
- Roda tudo na sua máquina. A **única** coisa que sai é a pergunta enviada ao
  agente `avancado` — e some da lista com `nuvem.ativo: false`.
- Home Assistant em modo `mock`: nada de credencial de casa no repo.
- O que ainda **não** existe: HTTPS/TLS (é LAN), rate limit, e rotação
  automática de token. Antes de expor pra internet (Cloudflare Tunnel), isso
  precisa ser revisto.
