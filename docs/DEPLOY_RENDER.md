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
- health check em `/healthz/`
- start com `gunicorn`

## Hosts e CSRF

O funcionamento normal em producao depende de `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` contendo todos os dominios publicos usados pelo cliente.

Valores esperados hoje:

```text
ALLOWED_HOSTS=prato-delivery.onrender.com,www.pratodelivery.com.br,pratodelivery.com.br
CSRF_TRUSTED_ORIGINS=https://prato-delivery.onrender.com,https://www.pratodelivery.com.br,https://pratodelivery.com.br
```

Esses valores estao no `render.yaml`. O `config/settings.py` tambem adiciona esses mesmos dominios como fallback defensivo, porque o painel do Render pode manter variaveis antigas quando o servico ja existe.

Nao use `ALLOWED_HOSTS=*` em producao.

## Healthcheck

O endpoint de saude e:

```text
/healthz/
```

Ele retorna `ok` em texto puro e nao acessa banco, templates, cardapio nem arquivos estaticos. Ha um middleware no inicio da pilha para responder somente esse caminho antes de `SecurityMiddleware`, porque o health check interno do Render pode chegar com Host interno e HTTP, diferente dos dominios publicos.

As paginas reais continuam passando pelo fluxo normal de seguranca do Django.

## Fluxo sugerido

1. Suba o repositorio correto, com a raiz deste projeto como Git root.
2. No Render, crie o servico a partir do `render.yaml`.
3. Ajuste `RESTAURANT_WHATSAPP`.
4. Revise o dominio publico gerado e confirme `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.
5. Rode um smoke test em `/healthz/`, `/`, `/checkout/` e `/admin/`.

## Banco local x producao

- Local: SQLite via `.env`
- Producao: PostgreSQL via `DATABASE_URL`

Nao use o `db.sqlite3` do desenvolvimento em producao.
