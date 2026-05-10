# Estrutura do Projeto

## Pastas principais

- `config/`: configuracao Django, settings, URLs e WSGI/ASGI
- `pedidos/`: dominio principal da aplicacao, com models, views, URLs, forms e testes
- `templates/`: templates Django
- `static/`: assets fonte
- `media/`: uploads locais
- `scripts/`: bootstrap e execucao local com `.venv`
- `docs/`: onboarding tecnico, desenvolvimento local e deploy

## Fluxos relevantes

- Cardapio e checkout: `pedidos/views.py`
- Criacao de pedido: `pedidos/views.py`
- Painel da cozinha: `pedidos/views.py`
- Gestao de pratos e pedidos: `pedidos/admin.py` e views administrativas
- Geocoding, bairros e mapa: `pedidos/views.py` e `pedidos/data/`

## Observacao importante

Havia um diretorio legado `PRATO-DELIVERY-ONLINE/` contendo apenas metadados Git fora da raiz correta do projeto. Ele foi tratado como artefato legado e nao deve ser usado como raiz do repositorio.
