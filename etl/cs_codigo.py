import re

# Caso 1: "CS" seguido de código de 6 dígitos, aceitando "0" digitado como
# letra "O"/"o" (typo comum) e zeros/O extras à esquerda como padding.
CS_PATTERN = re.compile(r"CS\s*[0Oo]*([0-9Oo]{6})(?!\d)", re.IGNORECASE)

# Caso 2: código substituído por "H" + ano + sequência (10 dígitos), ex.:
# "CS H2025021498". O código CS correto são os últimos 6 dígitos.
H_PATTERN = re.compile(r"\bH(\d{10})\b")

_ZERO_TYPO_TABLE = str.maketrans({"O": "0", "o": "0"})


def extrair_cs(descricao: str) -> str | None:
    descricao = descricao or ""

    match_cs = CS_PATTERN.search(descricao)
    if match_cs:
        codigo_normalizado = match_cs.group(1).translate(_ZERO_TYPO_TABLE)
        return f"CS{codigo_normalizado}"

    match_h = H_PATTERN.search(descricao)
    if match_h:
        return f"CS{match_h.group(1)[-6:]}"

    return None
