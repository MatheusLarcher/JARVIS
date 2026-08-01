"""Corta o texto do LLM em pedaços faláveis enquanto ele ainda está escrevendo.

A ideia é não esperar a resposta inteira: assim que junta uma frase curta, já dá
pra mandar gerar o áudio. Os primeiros pedaços são bem curtos (a voz começa
rápido) e vão crescendo, porque pedaço maior tem prosódia melhor e menos
sobrecarga por chamada.

O texto chega token a token e um token pode ser só um pedaço de palavra
("del"+"imit"+"ada"), então nada é cortado antes da palavra fechar.

    ch = Chunker()
    for pedaco_de_texto in stream_do_llm:
        for falavel in ch.feed(pedaco_de_texto):
            gerar_audio(falavel)
    for falavel in ch.flush():
        gerar_audio(falavel)
"""
import re

# fim de frase: corta aqui de preferência, sai mais natural
_FIM_FRASE = re.compile(r"[.!?…](?=\s|$)|[:;](?=\s)")
# o que indica que a palavra anterior terminou
_FIM_PALAVRA = re.compile(r"[\s.!?…,:;]")
_PALAVRA = re.compile(r"\S+")


class Chunker:
    def __init__(self, primeiro: int = 3, maximo: int = 14, crescimento: float = 2.0):
        self.primeiro = primeiro
        self.maximo = maximo
        self.crescimento = crescimento
        self.buffer = ""
        self.enviados = 0

    def _alvo(self) -> int:
        """Quantas palavras o próximo pedaço precisa ter."""
        alvo = self.primeiro * (self.crescimento ** self.enviados)
        return int(min(self.maximo, alvo))

    def feed(self, texto: str):
        """Recebe mais texto do LLM e devolve os pedaços já faláveis."""
        self.buffer += texto
        while True:
            pedaco = self._proximo()
            if pedaco is None:
                return
            yield pedaco

    def _corta(self, ate: int) -> str:
        pedaco = self.buffer[:ate].strip()
        self.buffer = self.buffer[ate:].lstrip()
        if pedaco:
            self.enviados += 1
        return pedaco

    def _proximo(self) -> str | None:
        # posições reais das palavras no buffer (sem normalizar espaços, senão
        # o índice de corte não bate com o texto original)
        spans = [m.span() for m in _PALAVRA.finditer(self.buffer)]
        if not spans:
            return None
        # a última palavra pode estar chegando pela metade
        if not _FIM_PALAVRA.match(self.buffer[-1:]):
            spans = spans[:-1]
        if not spans:
            return None

        # fim de frase é o melhor lugar pra cortar — mesmo que seja curta
        # ("Pronto."), porque a voz começa antes
        limite = spans[min(len(spans), self.maximo) - 1][1]
        m = _FIM_FRASE.search(self.buffer, 0, limite)
        if m:
            pedaco = self._corta(m.end())
            return pedaco or None

        alvo = self._alvo()
        if len(spans) < alvo:
            return None
        pedaco = self._corta(spans[alvo - 1][1])
        return pedaco or None

    def flush(self):
        """O que sobrou no fim da resposta."""
        resto = self.buffer.strip()
        self.buffer = ""
        if resto:
            self.enviados += 1
            yield resto
