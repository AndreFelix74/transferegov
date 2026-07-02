PROPOSTA_URL = (
    "https://discricionarias.transferegov.sistema.gov.br/voluntarias/"
    "ConsultarProposta/ResultadoDaConsultaDePropostaDetalharProposta.do"
    "?idProposta={id_proposta}"
)


def link_proposta(id_proposta: str) -> str | None:
    if not id_proposta:
        return None
    id_proposta = str(id_proposta).strip()
    if not id_proposta:
        return None
    return PROPOSTA_URL.format(id_proposta=id_proposta)
