import hmac
import os
import time
import unicodedata
from collections import defaultdict, deque
from math import isqrt
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
 
# ---------------------------------------------------------------------------
# Configuração (tudo vem das variáveis de ambiente do Railway)
# ---------------------------------------------------------------------------
CHAVE_SECRETA = os.environ.get("CHAVE_SECRETA", "").strip().lower()
MENSAGEM_SECRETA = os.environ.get(
    "MENSAGEM_SECRETA",
    "A caixa abriu. Anote no seu diário como você descobriu a chave.",
)

if not CHAVE_SECRETA or not CHAVE_SECRETA.isalpha():
    raise RuntimeError(
        "Defina a variável de ambiente CHAVE_SECRETA (só letras de a a z)."
    )

TAMANHO_MAXIMO = 40
TENTATIVAS_POR_MINUTO = 20
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

# Sem /docs, /redoc e /openapi.json: os alunos só enxergam a interface.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------------------
# A caixa-preta
# ---------------------------------------------------------------------------
ALFABETO = "abcdefghijklmnopqrstuvwxyz"


def crypto_vigenere(word, key):
    crypto = ""
    aux = 0
    for p in word:
        if aux > len(key) - 1:
            aux = 0
        k = key[aux]
        crypto += ALFABETO[(ALFABETO.find(p) + ALFABETO.find(k)) % 26]
        aux += 1
    return crypto


def swap(word):
    swapped_word = list(word)
    start = 1
    end = len(word) - 2
    while start < end:  # "!=" travava em palavras de tamanho par
        swapped_word[start], swapped_word[end] = swapped_word[end], swapped_word[start]
        start += 1
        end -= 1
    return "".join(swapped_word)


def is_prime(n):
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, isqrt(n) + 1, 2):
        if n % i == 0:
            return False
    return True


def clip_consonants_vogals(word):
    vogais = "aeiou"
    resultado_vogais = ""
    resultado_cw = ""
    for letter in word:
        if letter in vogais:
            resultado_vogais += letter
        else:
            resultado_cw += letter
    if is_prime(len(word)):
        return resultado_cw
    return resultado_vogais


def misterio(word, key):
    vigenere = crypto_vigenere(word, key)
    swapped = swap(word)
    clipped = clip_consonants_vogals(word)
    return vigenere + swapped + clipped


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos (ç -> c, ã -> a). Recusa o que não for a-z."""
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    if not texto:
        raise HTTPException(422, "Digite pelo menos uma letra.")
    if len(texto) > TAMANHO_MAXIMO:
        raise HTTPException(422, f"Use no máximo {TAMANHO_MAXIMO} letras.")
    if not all(c in ALFABETO for c in texto):
        raise HTTPException(422, "Use só letras, sem espaços, números ou símbolos.")
    return texto


_tentativas: dict[str, deque] = defaultdict(deque)


def limitar_tentativas(request: Request) -> None:
    """Freio simples contra força bruta na rota de abrir a caixa."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    ip = encaminhado.split(",")[0].strip() or (request.client.host if request.client else "?")
    agora = time.monotonic()
    fila = _tentativas[ip]
    while fila and agora - fila[0] > 60:
        fila.popleft()
    if len(fila) >= TENTATIVAS_POR_MINUTO:
        raise HTTPException(429, "Muitas tentativas. Espere um minuto e pense na próxima.")
    fila.append(agora)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
class Palavra(BaseModel):
    palavra: str


class Chave(BaseModel):
    chave: str


@app.get("/", include_in_schema=False)
def pagina():
    return FileResponse(INDEX_HTML)


@app.post("/api/misterio")
def rodar_misterio(dados: Palavra):
    palavra = normalizar(dados.palavra)
    return {"entrada": palavra, "saida": misterio(palavra, CHAVE_SECRETA)}


@app.post("/api/abrir")
def abrir_caixa(dados: Chave, request: Request):
    limitar_tentativas(request)
    chave = normalizar(dados.chave)
    if hmac.compare_digest(chave, CHAVE_SECRETA):
        return {"aberta": True, "mensagem": MENSAGEM_SECRETA}
    return {"aberta": False}
