# API de Pedidos

Esta API expõe pedidos cadastrados no sistema em JSON para consumo por outro app.

O escopo é somente leitura. A API não cria, altera, cancela, imprime, gera ZPL nem dispara qualquer fluxo operacional de pedido.

## Base URL

Em ambiente local:

```text
http://127.0.0.1:8000
```

Em produção, use o domínio da aplicação.

## Autenticação

A API não é pública.

Os endpoints exigem chave de acesso criada na guia:

```text
/controle/ajustes/?aba=api
```

O login do Django não autentica os endpoints JSON da API de pedidos. Mesmo um usuário logado precisa enviar uma chave válida.

A chave pode ser enviada de duas formas:

```http
Authorization: Bearer SUA_CHAVE
```

ou:

```text
X-API-Key: SUA_CHAVE
```

Sem chave ou com chave inválida, a API retorna:

```json
{
  "ok": false,
  "error": "invalid_api_key"
}
```

## Gerenciamento de Chaves

As chaves são gerenciadas na guia API da tela de ajustes:

```text
/controle/ajustes/?aba=api
```

Na criação, informe um nome para identificar a integração. A chave completa é exibida apenas uma vez, logo após salvar.

Depois disso, a tela mostra:

- nome da chave;
- prefixo da chave;
- usuário que criou;
- data do último uso;
- botão para exclusão.

Internamente, o sistema armazena somente o hash SHA-256 da chave. A chave completa não pode ser recuperada depois da criação. Se ela for perdida, exclua a antiga e crie uma nova.

## Endpoints

### Listar Pedidos

```http
GET /api/pedidos/
Authorization: Bearer SUA_CHAVE
```

Retorna todos os pedidos ordenados do mais recente para o mais antigo.

Resposta:

```json
{
  "count": 1,
  "pedidos": [
    {
      "id": 1,
      "numero": 2240,
      "nome_cliente": "Cliente API",
      "telefone": "64999999999",
      "cliente_id": null,
      "rua": "Rua API",
      "numero_endereco": "123",
      "bairro": "Centro",
      "cidade": "Rio Verde",
      "estado": "GO",
      "endereco_formatado": "Rua API, 123, Centro, Rio Verde - GO",
      "latitude": "-17.7923000",
      "longitude": "-50.9192000",
      "endereco": "Rua API, 123 - Centro, Rio Verde - GO",
      "complemento": "Casa",
      "lote_quadra": "Qd. 1 Lt. 2",
      "ponto_referencia": "Portao azul",
      "tipo_coleta": "entrega",
      "tipo_coleta_label": "Entrega",
      "icone_pedido": "img/Icones_pedidos/1.svg",
      "forma_pagamento": "pix",
      "forma_pagamento_label": "Online Pix",
      "enviar_talheres": false,
      "observacao_geral": "Sem cebola",
      "status": "em_preparo",
      "status_label": "Em preparo",
      "distancia_km": "4.20",
      "valor_frete": "10.00",
      "total_sem_desconto": "45.00",
      "promocao_descricao": "Promocao teste",
      "promocao_desconto": "5.00",
      "cupom_id": 1,
      "cupom_codigo": "API10",
      "cupom_desconto": "10.00",
      "total": "30.00",
      "public_token": "token-publico-do-pedido",
      "criado_em": "2026-05-15T12:00:00Z",
      "producao_iniciada_em": "2026-05-15T12:05:00Z",
      "entregador_solicitado": true,
      "status_label_contextual": "Em preparo",
      "has_coordinates": true,
      "google_maps_route_url": "https://www.google.com/maps/dir/?api=1&origin=...&destination=...&travelmode=driving",
      "icone_pedido_url": "/static/img/Icones_pedidos/1.svg",
      "is_retirada": false,
      "stage_labels": [
        {
          "status": "novo",
          "number": "1",
          "label": "Pedido recebido"
        }
      ],
      "cupom": {
        "id": 1,
        "codigo": "API10",
        "descricao": "Desconto API",
        "tipo_desconto": "valor_fixo",
        "valor": "10.00",
        "valor_minimo_pedido": "30.00",
        "ativo": true
      },
      "itens": [
        {
          "id": 1,
          "prato_id": 10,
          "bebida_id": null,
          "adicional_id": null,
          "nome_prato_snapshot": "Marmita API",
          "variacao_nome_snapshot": "Grande",
          "preco_snapshot": "35.00",
          "quantidade": 1,
          "observacao": "Arroz extra",
          "subtotal": "35.00"
        }
      ]
    }
  ]
}
```

### Detalhar Pedido

```http
GET /api/pedidos/<id>/
Authorization: Bearer SUA_CHAVE
```

Retorna um pedido específico com os mesmos campos da listagem.

Resposta:

```json
{
  "pedido": {
    "id": 1,
    "numero": 2240,
    "nome_cliente": "Cliente API",
    "itens": []
  }
}
```

Se o pedido não existir, retorna `404`.

## Filtros

Os filtros são opcionais e podem ser combinados.

| Query string | Exemplo | Descrição |
| --- | --- | --- |
| `status` | `/api/pedidos/?status=em_preparo` | Filtra pelo status persistido do pedido. |
| `tipo_coleta` | `/api/pedidos/?tipo_coleta=entrega` | Filtra por `entrega` ou `retirada`. |
| `criado_em` | `/api/pedidos/?criado_em=2026-05-15` | Filtra pela data de criação no formato `YYYY-MM-DD`. |
| `numero` | `/api/pedidos/?numero=2240` | Filtra pelo número do pedido. |
| `telefone` | `/api/pedidos/?telefone=64999999999` | Busca parcial no telefone do cliente. |

Exemplo combinando filtros:

```http
GET /api/pedidos/?status=em_preparo&tipo_coleta=entrega&telefone=9999
```

## Campos do Pedido

| Campo | Tipo JSON | Observação |
| --- | --- | --- |
| `id` | number | ID interno do pedido. |
| `numero` | number/null | Número operacional do pedido. |
| `nome_cliente` | string | Nome salvo no pedido. |
| `telefone` | string | Telefone salvo no pedido. |
| `cliente_id` | number/null | ID do cliente relacionado, quando houver. |
| `rua` | string | Rua persistida. |
| `numero_endereco` | string | Número do endereço. |
| `bairro` | string | Bairro. |
| `cidade` | string | Cidade. |
| `estado` | string | Estado. |
| `endereco_formatado` | string | Endereço formatado pelo fluxo atual. |
| `latitude` | string/null | Decimal serializado como string. |
| `longitude` | string/null | Decimal serializado como string. |
| `endereco` | string | Endereço completo salvo. |
| `complemento` | string | Complemento. |
| `lote_quadra` | string | Lote/quadra. |
| `ponto_referencia` | string | Ponto de referência. |
| `tipo_coleta` | string | Valor persistido, como `entrega` ou `retirada`. |
| `tipo_coleta_label` | string | Label do choice do Django. |
| `icone_pedido` | string | Caminho persistido do ícone. |
| `forma_pagamento` | string | Valor persistido da forma de pagamento. |
| `forma_pagamento_label` | string | Label do choice do Django. |
| `enviar_talheres` | boolean | Preferência do cliente. |
| `observacao_geral` | string | Observação geral. |
| `status` | string | Valor persistido do status. |
| `status_label` | string | Label padrão do status. |
| `distancia_km` | string | Decimal serializado como string. |
| `valor_frete` | string | Decimal serializado como string. |
| `total_sem_desconto` | string | Decimal serializado como string. |
| `promocao_descricao` | string | Descrição da promoção aplicada. |
| `promocao_desconto` | string | Decimal serializado como string. |
| `cupom_id` | number/null | ID do cupom relacionado. |
| `cupom_codigo` | string | Código do cupom salvo no pedido. |
| `cupom_desconto` | string | Decimal serializado como string. |
| `total` | string | Decimal serializado como string. |
| `public_token` | string | Token público já existente do pedido. |
| `criado_em` | string | Data/hora em ISO-8601. |
| `producao_iniciada_em` | string/null | Data/hora em ISO-8601. |
| `entregador_solicitado` | boolean | Estado persistido no pedido. |

## Dados Derivados e Contextuais

| Campo | Tipo JSON | Observação |
| --- | --- | --- |
| `status_label_contextual` | string | Label contextual usado pelo projeto. |
| `has_coordinates` | boolean | Indica se latitude e longitude existem. |
| `google_maps_route_url` | string | URL de rota calculada com helpers atuais do projeto. |
| `icone_pedido_url` | string | URL pública do ícone. |
| `is_retirada` | boolean | Indica se o pedido é retirada. |
| `stage_labels` | array | Etapas contextuais do pedido. |

## Campos dos Itens

Cada pedido inclui `itens` aninhados.

| Campo | Tipo JSON | Observação |
| --- | --- | --- |
| `id` | number | ID do item. |
| `prato_id` | number/null | ID do prato relacionado, quando houver. |
| `bebida_id` | number/null | ID da bebida relacionada, quando houver. |
| `adicional_id` | number/null | ID do adicional relacionado, quando houver. |
| `nome_prato_snapshot` | string | Nome salvo no momento do pedido. |
| `variacao_nome_snapshot` | string | Variação salva no momento do pedido. |
| `preco_snapshot` | string | Decimal serializado como string. |
| `quantidade` | number | Quantidade do item. |
| `observacao` | string | Observação do item. |
| `subtotal` | string | Decimal serializado como string. |

## Cupom

Quando o pedido tem cupom relacionado, o campo `cupom` retorna:

| Campo | Tipo JSON |
| --- | --- |
| `id` | number |
| `codigo` | string |
| `descricao` | string |
| `tipo_desconto` | string |
| `valor` | string |
| `valor_minimo_pedido` | string |
| `ativo` | boolean |

Quando não há cupom relacionado, `cupom` retorna `null`.

## Serialização de Valores

Valores decimais são serializados como string para preservar precisão:

```json
{
  "valor_frete": "10.00",
  "total": "30.00",
  "latitude": "-17.7923000"
}
```

Datas são serializadas pelo encoder JSON do Django em ISO-8601.

## Teste Local

Suba o servidor:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Crie uma chave em Ajustes:

```text
http://127.0.0.1:8000/controle/ajustes/?aba=api
```

Consulte a API enviando a chave:

```text
http://127.0.0.1:8000/api/pedidos/
http://127.0.0.1:8000/api/pedidos/1/
```

Rode os testes:

```powershell
.\.venv\Scripts\python.exe manage.py test pedidos
```
