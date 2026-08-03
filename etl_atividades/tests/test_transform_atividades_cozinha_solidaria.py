"""Testes das colunas derivadas codigo_cozinha / acao / refeicao."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from etl_atividades.transform_atividades_cozinha_solidaria import (
    extract_acao_refeicao,
    extract_codigo_cozinha,
)


def test_extract_codigo_cozinha_formato_normal():
    cozinha = "(CS000123) Cozinha Comunitária Centro (São Paulo)"
    assert extract_codigo_cozinha(cozinha) == "CS000123"


def test_extract_acao_refeicao_preparo_almoco():
    acao, refeicao = extract_acao_refeicao(
        "Preparo Almoço Arroz carreteiro (Kg)"
    )
    assert acao == "Preparo"
    assert refeicao == "Almoço"


def test_extract_acao_refeicao_distribuicao_jantar():
    acao, refeicao = extract_acao_refeicao(
        "Distribuição Jantar Sopa de legumes"
    )
    assert acao == "Distribuição"
    assert refeicao == "Jantar"


def test_extract_acao_refeicao_vazio_sem_warning():
    buf = io.StringIO()
    with redirect_stderr(buf):
        acao, refeicao = extract_acao_refeicao("")
    assert acao == ""
    assert refeicao == ""
    assert buf.getvalue() == ""


def test_extract_acao_refeicao_fora_do_vocabulario_com_warning():
    frase = "Texto sem padrão esperado"
    buf = io.StringIO()
    with redirect_stderr(buf):
        acao, refeicao = extract_acao_refeicao(frase)
    assert acao == ""
    assert refeicao == ""
    err = buf.getvalue()
    assert "aviso:" in err
    assert frase in err


if __name__ == "__main__":
    test_extract_codigo_cozinha_formato_normal()
    test_extract_acao_refeicao_preparo_almoco()
    test_extract_acao_refeicao_distribuicao_jantar()
    test_extract_acao_refeicao_vazio_sem_warning()
    test_extract_acao_refeicao_fora_do_vocabulario_com_warning()
    print("OK: todos os testes passaram.")
