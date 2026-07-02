def padronizar_nr_proposta(nr_proposta: str) -> str | None:
    if nr_proposta is None:
        return None
    text = str(nr_proposta).strip()
    if not text:
        return None
    if "/" not in text:
        return text
    numero, ano = text.split("/", 1)
    numero = numero.strip()
    ano = ano.strip()
    if not numero.isdigit():
        return text
    return f"{str(numero).zfill(6)}/{ano}"
