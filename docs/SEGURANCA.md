# Segurança e privacidade

O que **não** pode entrar no repositório, o que foi encontrado numa auditoria
antes de abrir o projeto, e o que fazer se algo vazar.

## O que nunca vai pro git

| O quê | Onde fica | Por quê |
|---|---|---|
| Chaves de API (OpenAI, DeepSeek, Home Assistant) | `config/.env` | acesso pago/privado em nome seu |
| Tokens dos aparelhos | `config/devices.yml` | quem tem o token fala com o seu assistente |
| Referência da voz clonada | `server/data/voice/` | é a voz de uma pessoa real |
| Gravações das suas falas | `server/data/gravacoes/` | áudio seu, dentro de casa |
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

**3. Voz clonada versionada — decisão sua.**
`server/data/library/` tem 34 WAV com a voz clonada falando ("Pronto.",
"Bom dia."…). A *referência* nunca foi versionada, mas esses arquivos são
saída dela. Publicar = distribuir um clone de voz. Se a voz de referência é de
outra pessoa, há consentimento de terceiro envolvido.

Se decidir tirar: `git rm -r --cached server/data/library`, adicionar ao
`.gitignore` e rodar `python server/scripts/build_library.py` depois de clonar
— o JARVIS continua funcionando, e sem os wavs ele cai no TTS na hora
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
