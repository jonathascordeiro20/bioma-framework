# Publicando o bioma-micro no PyPI

Artefatos da release 1.0.0 (já compilados e validados com `twine check` + smoke test):

- `target/wheels/bioma_micro-1.0.0-cp38-abi3-win_amd64.whl` — wheel abi3, cobre CPython ≥ 3.8 no Windows
- `target/wheels/bioma_micro-1.0.0.tar.gz` — sdist (Linux/macOS compilam via Rust automaticamente)

## Passo único que falta: o token

1. Crie um API token em https://pypi.org/manage/account/token/ (escopo "Entire account"
   para a primeira publicação; depois restrinja ao projeto `bioma-micro`).
2. Rode:

```powershell
cd c:\Users\jonat\A.N.I.M.A\workspace\bioma_micro
$env:MATURIN_PYPI_TOKEN = "pypi-AgEIcHlwaS5vcmc..."   # seu token
maturin upload target/wheels/bioma_micro-1.0.0-cp38-abi3-win_amd64.whl target/wheels/bioma_micro-1.0.0.tar.gz
```

3. Verifique: `pip install bioma-micro` num venv limpo.

> Não suba o wheel antigo `cp312-cp312` — o abi3 o substitui e cobre 3.8→3.13.

## Wheels Linux/macOS (adoção total)

O sdist já permite `pip install bioma-micro` em qualquer plataforma com Rust. Para
wheels prontos multi-plataforma, o caminho padrão é GitHub Actions com
`PyO3/maturin-action` (matriz linux/musllinux/macos/windows) publicando via
`maturin upload` — adicione quando o repo público existir.
