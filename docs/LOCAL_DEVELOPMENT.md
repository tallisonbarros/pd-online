# Desenvolvimento Local

## Requisitos

- Python 3.12
- PowerShell no Windows ou Bash no macOS/Linux

## Bootstrap rapido

### Windows

```powershell
.\scripts\stop-dev.ps1
.\scripts\bootstrap.ps1
.\scripts\dev.ps1
```

### macOS ou Linux

```bash
chmod +x scripts/*.sh
./scripts/bootstrap.sh
./scripts/dev.sh
```

Os scripts fazem:

1. criacao da `.venv`
2. instalacao de `requirements-dev.txt`
3. copia de `.env.example` para `.env`, se necessario
4. aplicacao das migracoes
5. limpeza de instancias antigas do projeto
6. inicializacao do servidor local sem autoreload

## Regra operacional

No Windows, nao use `python manage.py runserver` manualmente como fluxo normal. O caminho suportado e `scripts/dev.ps1`, para evitar processos antigos presos na mesma porta.

## Fluxo manual

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\scripts\stop-dev.ps1
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

### macOS ou Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

## Endpoints principais

- Cardapio: `http://127.0.0.1:8000/`
- Checkout: `http://127.0.0.1:8000/checkout/`
- Cozinha dashboard: `http://127.0.0.1:8000/cozinha/`
- Admin Django: `http://127.0.0.1:8000/admin/`

## Limpeza manual

Se houver qualquer suspeita de servidor antigo:

```powershell
.\scripts\stop-dev.ps1
```
