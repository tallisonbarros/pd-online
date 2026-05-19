# Plano: sugerir enderecos de cliente no pedido novo

## Objetivo

No modal de novo pedido em `controle/pedidos`, ao preencher um telefone que ja pertence a um cliente conhecido, importar o nome do cliente, oferecer os enderecos ja usados por esse cliente e permitir aplicar um deles ao pedido rascunho.

## Comportamento esperado

1. Atendente cria um novo pedido pelo botao `+ Adicionar pedido`.
2. Atendente edita o campo `Telefone`.
3. Sistema normaliza o telefone e busca cliente conhecido.
4. Se encontrar cliente conhecido, o pedido novo recebe o nome desse cliente.
5. Se houver cliente com enderecos salvos, abre um modal pequeno:
   - pergunta se deseja usar um endereco conhecido;
   - lista os enderecos do cliente, ordenados do mais recente para o mais antigo;
   - permite selecionar um endereco ou ignorar.
6. Ao selecionar um endereco, o pedido novo recebe:
   - tipo de coleta `entrega`;
   - rua;
   - numero;
   - bairro;
   - cidade;
   - estado;
   - endereco formatado;
   - complemento;
   - lote/quadra;
   - ponto de referencia;
   - latitude/longitude, quando existirem.
7. O modal do pedido e atualizado com o nome e o endereco aplicado.

## Escopo recomendado

Implementar primeiro apenas para pedidos em `rascunho`, especialmente os criados por `pedido_novo_admin`.

Evitar abrir sugestao em pedidos ja em producao, finalizados ou cancelados para nao atrapalhar a operacao.

## Backend

### Novo endpoint

Criar endpoint interno, protegido por staff:

```text
GET /controle/api/clientes/enderecos/?telefone=...
```

Sugestao de nome Django:

```python
path("controle/api/clientes/enderecos/", views.api_cliente_enderecos_por_telefone, name="api_cliente_enderecos_por_telefone")
```

### Logica

1. Ler `telefone` da query string.
2. Usar `normalize_phone` de `pedidos.order_services`.
3. Buscar:

```python
Cliente.objects.prefetch_related("enderecos").filter(telefone_normalizado=telefone_normalizado).first()
```

4. Se nao encontrar cliente ou nao houver enderecos, retornar:

```json
{
  "ok": true,
  "cliente": null,
  "enderecos": []
}
```

5. Se encontrar, retornar dados seguros e suficientes:

```json
{
  "ok": true,
  "cliente": {
    "id": 1,
    "nome": "Beth",
    "telefone": "(64) 99999-9999"
  },
  "enderecos": [
    {
      "id": 10,
      "endereco": "Rua X, 123 - Centro, Rio Verde - GO",
      "endereco_formatado": "Rua X, 123 - Centro, Rio Verde - GO",
      "rua": "Rua X",
      "numero_endereco": "123",
      "bairro": "Centro",
      "cidade": "Rio Verde",
      "estado": "GO",
      "complemento": "Casa",
      "lote_quadra": "",
      "ponto_referencia": "Perto da escola",
      "latitude": "-17.0000000",
      "longitude": "-50.0000000",
      "ultimo_uso_em": "2026-05-18T12:00:00-03:00"
    }
  ]
}
```

### Aplicacao do endereco

Reaproveitar o endpoint existente:

```text
POST /controle/pedido/<id>/entrega/
```

Esse endpoint ja atualiza endereco e recalcula frete quando ha coordenadas. A selecao do endereco salvo pode postar para ele com os campos do endereco escolhido.

## Frontend

Arquivo principal:

```text
static/js/pedido_detail_modal.js
```

### Gatilho

Apos salvar inline o campo `telefone`, se o pedido atual for rascunho ou novo pedido:

1. chamar endpoint de enderecos por telefone;
2. se retornar `cliente.nome`, importar/preencher o nome do cliente no pedido novo;
3. se `enderecos.length > 0`, abrir modal de selecao.

Possiveis formas de identificar novo pedido:

- usar `is_new_order` no template e expor um atributo no modal, por exemplo:

```html
<section data-pedido-new-order="true">
```

ou

```html
<span data-order-status="rascunho">
```

### Modal de selecao

Pode ser criado dinamicamente no JS, similar ao `confirmModal`, ou usando markup/template no HTML.

Conteudo sugerido:

```text
Endereco encontrado
Encontramos enderecos usados por Beth. Deseja usar um deles neste pedido?
```

Cada item deve mostrar:

- endereco principal;
- complemento/lote/referencia, quando existirem;
- ultimo uso, se relevante.

Acoes:

- `Usar este endereco`;
- `Ignorar`;
- `Cadastrar outro endereco`.

### Ao selecionar endereco

Postar para `atualizar_entrega_pedido`:

```text
tipo_coleta=entrega
rua=...
numero=...
bairro=...
cidade=...
estado=...
endereco_formatado=...
latitude=...
longitude=...
complemento=...
lote_quadra=...
ponto_referencia=...
```

Depois aplicar o payload retornado com `applyModalPayload`.

### Ao reconhecer cliente pelo telefone

Quando o endpoint retornar um cliente conhecido, o frontend deve preencher tambem o campo de nome do pedido novo com `cliente.nome`, antes ou junto da sugestao de endereco. Esse preenchimento deve acontecer mesmo que o cliente nao tenha enderecos salvos, desde que o telefone normalizado identifique um cliente.

## UX

Regras para nao incomodar:

- mostrar a sugestao apenas uma vez por telefone digitado;
- nao mostrar se nao houver enderecos;
- nao mostrar se o pedido ja possui endereco de entrega diferente de `Retirada no local`, a menos que seja claramente pedido novo;
- permitir ignorar sem bloquear o fluxo.

Texto sugerido:

```text
Endereco encontrado
Esse telefone ja tem enderecos salvos. Quer usar um deles neste pedido?
```

Botao:

```text
Usar endereco
```

## Testes recomendados

### Backend

Adicionar testes em `pedidos/tests.py`:

1. telefone desconhecido retorna lista vazia;
2. telefone conhecido retorna cliente e enderecos;
3. telefone com mascara busca pelo normalizado;
4. endpoint exige usuario staff/logado;
5. enderecos retornam ordenados por `ultimo_uso_em` desc.

### Frontend manual

1. Criar cliente com pedido anterior e endereco.
2. Abrir `controle/pedidos`.
3. Clicar `+ Adicionar pedido`.
4. Editar telefone para o telefone do cliente.
5. Confirmar que o nome do cliente e preenchido no pedido novo.
6. Confirmar que modal de enderecos aparece.
7. Selecionar endereco.
8. Confirmar que o pedido muda para entrega e preenche o endereco.
9. Confirmar que frete/distancia recalculam quando ha coordenadas.
10. Confirmar que `Ignorar` nao muda o endereco do pedido.

## Complexidade

Classificacao: media.

Backend: media-baixa, porque os models e normalizacao ja existem.

Frontend: media, porque precisa encaixar no modal atual sem criar comportamento invasivo.

Estimativa:

- versao simples funcional: 4 a 6 horas;
- versao polida com testes e estados de erro/loading: 1 dia.

## Riscos e cuidados

- Pedidos em rascunho hoje nao vinculam cliente automaticamente em `sync_customer_from_order`; por isso a busca deve ser direta por telefone normalizado.
- Enderecos sem coordenadas podem nao recalcular frete automaticamente; o fluxo deve permitir ajuste manual pelo editor de endereco.
- Se houver muitos enderecos, limitar a lista inicial, por exemplo os 5 mais recentes.
- Evitar abrir a sugestao repetidamente ao editar o mesmo telefone.
