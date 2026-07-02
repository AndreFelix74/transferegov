import re

CS_PATTERN = re.compile(r"CS\s*0*(\d{6})", re.IGNORECASE)


def extrair_cs(descricao: str) -> str | None:
    match = CS_PATTERN.search(descricao or "")
    if not match:
        return None
    return f"CS{match.group(1)}"
