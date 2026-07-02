def natureza_despesa_de_codigo(codigo: str) -> str | None:
    if not codigo:
        return None
    text = str(codigo).strip()
    if not text:
        return None
    if text[0] == "3":
        return "CUSTEIO"
    if text[0] == "4":
        return "CAPITAL"
    return None
