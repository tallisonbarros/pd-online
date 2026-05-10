# PRATO-DELIVERY

Aplicacao Django para operacao de delivery do Prato Delivery, com cardapio mobile-first, checkout simplificado, criacao de pedido sem cadastro e painel interno de operacao.

## Stack

- Python 3.12
- Django 5
- SQLite no desenvolvimento
- PostgreSQL no Render via `DATABASE_URL`
- Django Templates + HTML/CSS/JavaScript
- WhiteNoise para arquivos estaticos
- Gunicorn no deploy

## Inicio rapido

### Windows PowerShell

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

No Windows, o fluxo oficial e suportado e sempre via script. Evite subir com `python manage.py runserver` manualmente, porque isso volta a abrir espaco para instancias antigas e comportamento inconsistente.

## Acesso local

- Cardapio: `http://127.0.0.1:8000/`
- Checkout: `http://127.0.0.1:8000/checkout/`
- Cozinha dashboard: `http://127.0.0.1:8000/cozinha/`
- Admin: `http://127.0.0.1:8000/admin/`

## Variaveis de ambiente

Use `.env` localmente. Modelo disponivel em `.env.example`.

- `DEBUG`: `True` ou `False`
- `SECRET_KEY`: chave secreta do Django
- `ALLOWED_HOSTS`: hosts separados por virgula
- `CSRF_TRUSTED_ORIGINS`: URLs separadas por virgula
- `DATABASE_URL`: `sqlite:///db.sqlite3` no dev ou URL PostgreSQL no Render
- `RESTAURANT_WHATSAPP`: numero no formato internacional, sem `+`
- `DELIVERY_ETA_MULTIPLIER`: calibracao do tempo estimado
- `DELIVERY_ETA_BUFFER_MINUTES`: buffer fixo em minutos
- `DELIVERY_ETA_SHORT_TRIP_KM`: limite de trecho curto
- `DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES`: penalidade adicional em trecho curto

## Documentacao

- Desenvolvimento local: [docs/LOCAL_DEVELOPMENT.md](C:/Users/talli/OneDrive/Documentos/Treinamentos/PD-ONLINE/PD-ONLINE_APP/docs/LOCAL_DEVELOPMENT.md:1)
- Deploy no Render: [docs/DEPLOY_RENDER.md](C:/Users/talli/OneDrive/Documentos/Treinamentos/PD-ONLINE/PD-ONLINE_APP/docs/DEPLOY_RENDER.md:1)
- Estrutura do projeto: [docs/PROJECT_STRUCTURE.md](C:/Users/talli/OneDrive/Documentos/Treinamentos/PD-ONLINE/PD-ONLINE_APP/docs/PROJECT_STRUCTURE.md:1)

## Operacao administrativa

Para criar um superusuario:

```bash
python manage.py createsuperuser
```

## Limpeza do ambiente local

Para encerrar qualquer servidor antigo deste projeto no Windows:

```powershell
.\scripts\stop-dev.ps1
```

No admin voce consegue:

- cadastrar e ativar pratos
- revisar pedidos
- ajustar status operacionais
- configurar faixas de frete

## Deploy

O projeto ja esta preparado para Render com PostgreSQL. O fluxo usa:

- `render.yaml`
- `Procfile`
- `requirements.txt`
- leitura de `DATABASE_URL`

Build:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

Start:

```bash
gunicorn config.wsgi:application
```
