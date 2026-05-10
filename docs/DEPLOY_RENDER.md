# Deploy no Render

## Stack de deploy

- Web service Python
- PostgreSQL gerenciado pelo Render
- `DATABASE_URL` injetada automaticamente
- arquivos estaticos servidos com WhiteNoise

## Arquivos usados no deploy

- `render.yaml`
- `Procfile`
- `requirements.txt`
- `config/settings.py`

## Variaveis de ambiente

Obrigatorias:

- `DEBUG=False`
- `SECRET_KEY`
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `RESTAURANT_WHATSAPP`

O `render.yaml` ja provisiona:

- app Python
- banco PostgreSQL
- build com `pip install`, `collectstatic` e `migrate`
- start com `gunicorn`

## Fluxo sugerido

1. Suba o repositorio correto, com a raiz deste projeto como Git root.
2. No Render, crie o servico a partir do `render.yaml`.
3. Ajuste `RESTAURANT_WHATSAPP`.
4. Revise o dominio publico gerado e confirme `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.
5. Rode um smoke test em `/`, `/checkout/` e `/admin/`.

## Banco local x producao

- Local: SQLite via `.env`
- Producao: PostgreSQL via `DATABASE_URL`

Nao use o `db.sqlite3` do desenvolvimento em producao.
