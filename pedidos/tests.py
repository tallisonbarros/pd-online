import json

from decimal import Decimal
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import AccessEvent, Adicional, Bebida, Cliente, ClienteTokenConflito, ConfiguracaoEntrega, Cupom, EnderecoCliente, FaixaFrete, ItemPedido, Pedido, PedidoApiKey, PedidoListaImpressao, Prato
from .order_services import create_order_items_from_payload, inherit_customer_from_known_tokens, sync_customer_from_order
from .utils import build_google_maps_route_url
from .views import ORDER_HISTORY_COOKIE, _calcular_frete_por_distancia


class ProductionHostSettingsTests(SimpleTestCase):
    def test_production_domains_are_allowed_even_with_env_override(self):
        self.assertIn("prato-delivery.onrender.com", settings.ALLOWED_HOSTS)
        self.assertIn("www.pratodelivery.com.br", settings.ALLOWED_HOSTS)
        self.assertIn("pratodelivery.com.br", settings.ALLOWED_HOSTS)
        self.assertIn("https://www.pratodelivery.com.br", settings.CSRF_TRUSTED_ORIGINS)


class GoogleMapsRouteUrlTests(TestCase):
    def setUp(self):
        config = ConfiguracaoEntrega.get_solo()
        config.origem_endereco = "Ponto confirmado no mapa"
        config.origem_latitude = Decimal("-17.7721260")
        config.origem_longitude = Decimal("-50.9102290")
        config.save()

    def test_uses_coordinates_when_available(self):
        order = SimpleNamespace(
            rua="Rua 7",
            numero_endereco="120",
            bairro="Setor Central",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua 7, 120 - Setor Central, Rio Verde - GO",
            latitude=Decimal("-17.7923"),
            longitude=Decimal("-50.9192"),
        )

        url = build_google_maps_route_url(order)
        parsed = parse_qs(urlparse(url).query)

        self.assertEqual(parsed.get("api"), ["1"])
        self.assertEqual(parsed.get("travelmode"), ["driving"])
        self.assertEqual(parsed.get("origin"), ["-17.7721260,-50.9102290"])
        self.assertEqual(parsed.get("destination"), ["-17.7923,-50.9192"])

    def test_uses_text_address_when_coordinates_are_missing(self):
        order = SimpleNamespace(
            rua="Rua 7",
            numero_endereco="120",
            bairro="Setor Central",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua 7, 120 - Setor Central, Rio Verde - GO",
            latitude=None,
            longitude=None,
        )

        url = build_google_maps_route_url(order)
        parsed = parse_qs(urlparse(url).query)
        destination = parsed.get("destination", [""])[0]

        self.assertEqual(parsed.get("origin"), ["-17.7721260,-50.9102290"])
        self.assertIn("Rua 7", destination)
        self.assertIn("120", destination)
        self.assertIn("Setor Central", destination)
        self.assertIn("Rio Verde", destination)
        self.assertIn("GO", destination)


class FaixaFreteTests(TestCase):
    def setUp(self):
        FaixaFrete.objects.bulk_create(
            [
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("5.00"), valor=Decimal("10.00"), ordem=10, ativo=True),
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("10.00"), valor=Decimal("20.00"), ordem=20, ativo=True),
                FaixaFrete(tipo=FaixaFrete.Tipo.ACIMA, km_limite=Decimal("10.00"), valor=Decimal("30.00"), ordem=30, ativo=True),
            ]
        )

    def test_frete_ate_cinco_km(self):
        valor, faixa = _calcular_frete_por_distancia(4.2)
        self.assertEqual(valor, Decimal("10.00"))
        self.assertEqual(faixa.tipo, FaixaFrete.Tipo.ATE)
        self.assertEqual(faixa.km_limite, Decimal("5.00"))

    def test_frete_entre_cinco_e_dez_km(self):
        valor, faixa = _calcular_frete_por_distancia(8.9)
        self.assertEqual(valor, Decimal("20.00"))
        self.assertEqual(faixa.tipo, FaixaFrete.Tipo.ATE)
        self.assertEqual(faixa.km_limite, Decimal("10.00"))

    def test_frete_acima_de_dez_km(self):
        valor, faixa = _calcular_frete_por_distancia(13.4)
        self.assertEqual(valor, Decimal("30.00"))
        self.assertEqual(faixa.tipo, FaixaFrete.Tipo.ACIMA)
        self.assertEqual(faixa.km_limite, Decimal("10.00"))


class OrderHeatmapApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="cozinha_teste",
            password="12345678",
            is_staff=True,
        )

    def _create_order(self, *, lat=None, lng=None, status=Pedido.Status.NOVO, days_ago=0):
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Teste",
            telefone="64999999999",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=status,
            latitude=lat,
            longitude=lng,
            total=Decimal("35.00"),
        )
        if days_ago:
            criado_em = timezone.now() - timedelta(days=days_ago)
            Pedido.objects.filter(pk=pedido.pk).update(criado_em=criado_em)
            pedido.refresh_from_db()
        return pedido

    def test_requires_staff_authentication(self):
        response = self.client.get("/dashboard/api/order-heatmap/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_returns_only_valid_points_for_default_period(self):
        self.client.force_login(self.staff_user)

        self._create_order(lat=Decimal("-17.7923000"), lng=Decimal("-50.9192000"))
        self._create_order(lat=Decimal("-17.7950000"), lng=Decimal("-50.9160000"), status=Pedido.Status.CANCELADO)
        self._create_order(lat=None, lng=None)
        self._create_order(lat=Decimal("-17.8010000"), lng=Decimal("-50.9270000"), days_ago=10)

        response = self.client.get("/dashboard/api/order-heatmap/")
        self.assertEqual(response.status_code, 200)
        points = response.json()
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["weight"], 1)
        self.assertAlmostEqual(points[0]["lat"], -17.7923, places=4)
        self.assertAlmostEqual(points[0]["lng"], -50.9192, places=4)

    def test_period_all_includes_older_points(self):
        self.client.force_login(self.staff_user)

        self._create_order(lat=Decimal("-17.7923000"), lng=Decimal("-50.9192000"))
        self._create_order(lat=Decimal("-17.8010000"), lng=Decimal("-50.9270000"), days_ago=10)

        response = self.client.get("/dashboard/api/order-heatmap/?period=all")
        self.assertEqual(response.status_code, 200)
        points = response.json()
        self.assertEqual(len(points), 2)


class CozinhaAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="cozinha_staff",
            password="12345678",
            is_staff=True,
        )

    def test_dashboard_requires_staff_authentication(self):
        response = self.client.get("/controle/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_live_orders_api_requires_staff_authentication(self):
        response = self.client.get("/controle/api/pedidos/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_access_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/")

        self.assertEqual(response.status_code, 200)

    def test_operation_metrics_count_plate_quantities_not_orders(self):
        self.client.force_login(self.staff_user)
        prato = Prato.objects.create(nome="Executivo", preco=Decimal("25.00"), ativo=True)
        bebida = Bebida.objects.create(nome="Agua", preco=Decimal("4.00"), ativo=True)
        adicional = Adicional.objects.create(nome="Farofa", preco=Decimal("5.00"), ativo=True)
        producao = Pedido.objects.create(
            nome_cliente="Cliente Producao",
            telefone="64999999999",
            endereco="Rua Producao",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("84.00"),
        )
        finalizado = Pedido.objects.create(
            nome_cliente="Cliente Entregue",
            telefone="64888888888",
            endereco="Rua Entregue",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("59.00"),
        )
        ItemPedido.objects.create(
            pedido=producao,
            prato=prato,
            nome_prato_snapshot="Executivo",
            preco_snapshot=Decimal("25.00"),
            quantidade=3,
        )
        ItemPedido.objects.create(
            pedido=producao,
            bebida=bebida,
            nome_prato_snapshot="Agua",
            preco_snapshot=Decimal("4.00"),
            quantidade=4,
        )
        ItemPedido.objects.create(
            pedido=producao,
            adicional=adicional,
            nome_prato_snapshot="Farofa",
            preco_snapshot=Decimal("5.00"),
            quantidade=2,
        )
        ItemPedido.objects.create(
            pedido=finalizado,
            prato=prato,
            nome_prato_snapshot="Executivo",
            preco_snapshot=Decimal("25.00"),
            quantidade=2,
        )
        ItemPedido.objects.create(
            pedido=finalizado,
            bebida=bebida,
            nome_prato_snapshot="Agua",
            preco_snapshot=Decimal("4.00"),
            quantidade=5,
        )

        response = self.client.get("/controle/api/operacao/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_para_producao"], 3)
        self.assertEqual(payload["entregues_hoje"], 2)
        self.assertEqual(payload["pratos_em_producao"], [{"nome": "Executivo", "quantidade": 3}])


class AccessMetricsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="metricas_staff",
            password="12345678",
            is_staff=True,
        )

    def _create_metric_order(self, tipo_coleta):
        return Pedido.objects.create(
            nome_cliente="Cliente Metricas",
            telefone="64999999999",
            rua="Rua Metricas",
            numero_endereco="10",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Metricas, 10 - Centro, Rio Verde - GO",
            tipo_coleta=tipo_coleta,
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.NOVO,
            total=Decimal("39.90"),
        )

    def test_metricas_page_requires_staff_authentication(self):
        response = self.client.get("/controle/metricas/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_metric_event_endpoint_records_sanitized_event(self):
        response = self.client.post(
            "/api/metrics/event/",
            data=json.dumps(
                {
                    "event_type": "add_to_cart",
                    "path": "/",
                    "item_type": "prato",
                    "item_id": 10,
                    "cart_items_count": 2,
                    "cart_total": "39.80",
                    "metadata": {"nome_cliente": "Nao deve virar campo dedicado", "origem": "cardapio"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        event = AccessEvent.objects.get()
        self.assertEqual(event.event_type, AccessEvent.EventType.ADD_TO_CART)
        self.assertEqual(event.path, "/")
        self.assertEqual(event.item_type, "prato")
        self.assertEqual(event.item_id, 10)
        self.assertEqual(event.cart_items_count, 2)
        self.assertEqual(event.cart_total, Decimal("39.80"))
        self.assertEqual(event.metadata["origem"], "cardapio")
        self.assertNotIn("nome_cliente", event.metadata)

    def test_metricas_page_shows_funnel_counts(self):
        self.client.force_login(self.staff_user)
        prato = Prato.objects.create(nome="Executivo", preco=Decimal("19.90"), ativo=True)
        today = timezone.now()
        events = [
            AccessEvent(event_type=AccessEvent.EventType.MENU_VIEW, path="/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.CART_VIEW, path="/carrinho/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.PICKUP_SUBMIT, path="/carrinho/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.CHECKOUT_VIEW, path="/checkout/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.ORDER_CREATED, path="/pedido/criar/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.PAGE_ACTIVE, path="/checkout/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.MENU_VIEW, path="/", session_key="b"),
            AccessEvent(event_type=AccessEvent.EventType.ADD_TO_CART, path="/", session_key="b", item_type="prato", item_id=prato.id),
        ]
        AccessEvent.objects.bulk_create(events)
        AccessEvent.objects.update(created_at=today)
        self._create_metric_order(Pedido.TipoColeta.ENTREGA)
        self._create_metric_order(Pedido.TipoColeta.RETIRADA)

        response = self.client.get("/controle/metricas/?period=7d")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metricas de acesso")
        self.assertContains(response, "Executivo")
        self.assertContains(response, "Retirada")
        self.assertContains(response, "Caixa")
        self.assertContains(response, "Visitantes que chegaram ao carrinho")
        self.assertContains(response, 'data-metric-value="retirada_orders_total">1</strong>')
        self.assertContains(response, 'data-metric-value="envio_orders_total">1</strong>')
        self.assertContains(response, 'data-metric-value="total_pedidos_metricas">2</strong>')
        self.assertContains(response, 'data-metric-value="envio_orders_share">50%</b>')
        self.assertContains(response, 'data-metric-value="retirada_orders_share">50%</b>')
        self.assertContains(response, "ops-kpi-card--fulfillment")
        self.assertContains(response, "Acessos unicos no periodo")
        self.assertContains(response, "Pedidos reais no periodo")
        self.assertContains(response, "Acessos recentes")
        self.assertContains(response, 'data-active-users-count>1</strong>')
        self.assertContains(response, "Acesso ao cardapio")
        self.assertNotContains(response, "Adicoes")
        content = response.content.decode()
        self.assertLess(content.index('data-metric-value="total_cardapio"'), content.index('data-metric-value="total_carrinho"'))
        self.assertLess(content.index('data-metric-value="total_carrinho"'), content.index('data-metric-value="total_checkout"'))
        self.assertLess(content.index('data-metric-value="total_checkout"'), content.index('data-metric-value="total_pedidos_metricas"'))
        self.assertLess(content.index('data-metric-value="total_pedidos_metricas"'), content.index('data-metric-value="envio_orders_total"'))
        self.assertLess(content.index('data-metric-value="envio_orders_total"'), content.index('data-metric-value="retirada_orders_total"'))
        self.assertContains(response, 'data-metrics-root')
        self.assertContains(response, "/controle/api/metricas/")

    def test_metricas_api_returns_live_payload(self):
        self.client.force_login(self.staff_user)
        prato = Prato.objects.create(nome="Executivo", preco=Decimal("19.90"), ativo=True)
        events = [
            AccessEvent(event_type=AccessEvent.EventType.MENU_VIEW, path="/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.CART_VIEW, path="/carrinho/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.PICKUP_SUBMIT, path="/carrinho/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.ADD_TO_CART, path="/", session_key="a", item_type="prato", item_id=prato.id),
            AccessEvent(event_type=AccessEvent.EventType.PAGE_ACTIVE, path="/", session_key="a"),
            AccessEvent(event_type=AccessEvent.EventType.PAGE_ACTIVE, path="/carrinho/", session_key="b"),
        ]
        AccessEvent.objects.bulk_create(events)
        AccessEvent.objects.update(created_at=timezone.now())
        self._create_metric_order(Pedido.TipoColeta.ENTREGA)
        self._create_metric_order(Pedido.TipoColeta.RETIRADA)

        response = self.client.get("/controle/api/metricas/?period=7d")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["periodo_key"], "7d")
        self.assertEqual(payload["kpis"]["total_cardapio"], 1)
        self.assertEqual(payload["kpis"]["total_carrinho"], 1)
        self.assertEqual(payload["kpis"]["total_retirada"], 1)
        self.assertEqual(payload["kpis"]["total_pedidos_metricas"], 2)
        self.assertEqual(payload["kpis"]["envio_orders_total"], 1)
        self.assertEqual(payload["kpis"]["retirada_orders_total"], 1)
        self.assertEqual(payload["kpis"]["envio_orders_share"], "50%")
        self.assertEqual(payload["kpis"]["retirada_orders_share"], "50%")
        self.assertNotIn("add_to_cart_total", payload["kpis"])
        self.assertEqual(payload["funnel_steps"][2]["label"], "Retirada")
        self.assertEqual(payload["funnel_steps"][3]["label"], "Caixa")
        self.assertEqual(payload["top_items"][0]["nome"], "Executivo")
        self.assertEqual(payload["active_users_count"], 2)
        self.assertEqual(payload["access_history"][0]["label"], "Item adicionado ao carrinho")
        self.assertNotIn("Usuario ativo", [row["label"] for row in payload["access_history"]])
        self.assertIn("updated_at", payload)


class PedidosReadOnlyApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="api_pedidos_staff",
            password="12345678",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="api_pedidos_regular",
            password="12345678",
            is_staff=False,
        )
        self.api_key, self.raw_api_key = PedidoApiKey.create_key("Teste API", self.staff_user)
        self.cupom = Cupom.objects.create(
            codigo="API10",
            descricao="Desconto API",
            tipo_desconto=Cupom.TipoDesconto.VALOR_FIXO,
            valor=Decimal("10.00"),
            valor_minimo_pedido=Decimal("30.00"),
            ativo=True,
        )
        self.pedido = Pedido.objects.create(
            nome_cliente="Cliente API",
            telefone="64999999999",
            rua="Rua API",
            numero_endereco="123",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco_formatado="Rua API, 123, Centro, Rio Verde - GO",
            latitude=Decimal("-17.7923000"),
            longitude=Decimal("-50.9192000"),
            endereco="Rua API, 123 - Centro, Rio Verde - GO",
            complemento="Casa",
            lote_quadra="Qd. 1 Lt. 2",
            ponto_referencia="Portao azul",
            tipo_coleta=Pedido.TipoColeta.ENTREGA,
            forma_pagamento=Pedido.FormaPagamento.PIX,
            enviar_talheres=False,
            observacao_geral="Sem cebola",
            status=Pedido.Status.EM_PREPARO,
            distancia_km=Decimal("4.20"),
            valor_frete=Decimal("10.00"),
            total_sem_desconto=Decimal("45.00"),
            promocao_descricao="Promocao teste",
            promocao_desconto=Decimal("5.00"),
            cupom=self.cupom,
            cupom_codigo=self.cupom.codigo,
            cupom_desconto=Decimal("10.00"),
            total=Decimal("30.00"),
            entregador_solicitado=True,
        )
        ItemPedido.objects.create(
            pedido=self.pedido,
            nome_prato_snapshot="Marmita API",
            variacao_nome_snapshot="Grande",
            preco_snapshot=Decimal("35.00"),
            quantidade=1,
            observacao="Arroz extra",
            subtotal=Decimal("35.00"),
        )

    def test_requires_api_key(self):
        response = self.client.get("/api/pedidos/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_api_key")

    def test_healthcheck_is_lightweight(self):
        response = self.client.get("/healthz/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_rejects_invalid_api_key_even_when_user_is_logged_in(self):
        self.client.force_login(self.regular_user)

        response = self.client.get("/api/pedidos/", HTTP_AUTHORIZATION="Bearer invalida")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_api_key")

    def test_authenticated_list_returns_orders(self):
        response = self.client.get("/api/pedidos/", HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertIsNone(payload["limit"])
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["pedidos"][0]["id"], self.pedido.id)
        self.assertIn("atualizado_em", payload["pedidos"][0])
        self.api_key.refresh_from_db()
        self.assertIsNotNone(self.api_key.ultimo_uso_em)

    def test_authenticated_list_supports_pagination_and_summary_fields(self):
        second = Pedido.objects.create(
            nome_cliente="Resumo API",
            telefone="64111111111",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.NOVO,
            total=Decimal("22.00"),
        )

        response = self.client.get(
            "/api/pedidos/?limit=1&offset=0&fields=summary",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}",
        )

        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["next_offset"], 1)
        self.assertTrue(payload["has_more"])
        self.assertEqual(len(payload["pedidos"]), 1)
        self.assertEqual(payload["pedidos"][0]["id"], second.id)
        self.assertNotIn("itens", payload["pedidos"][0])

    def test_authenticated_list_supports_updated_after_filter(self):
        cutoff = timezone.now() - timedelta(minutes=10)
        Pedido.objects.filter(id=self.pedido.id).update(atualizado_em=cutoff - timedelta(minutes=1))
        newer = Pedido.objects.create(
            nome_cliente="Novo Sync",
            telefone="64222222222",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.NOVO,
            total=Decimal("21.00"),
        )

        response = self.client.get(
            f"/api/pedidos/?updated_after={cutoff.isoformat()}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}",
        )

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["pedidos"][0]["id"], newer.id)

    def test_list_rate_limit_returns_retry_after(self):
        response = None
        for _ in range(13):
            response = self.client.get("/api/pedidos/", HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}")

        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertEqual(payload["error"], "rate_limited")
        self.assertEqual(payload["retry_after"], 60)
        self.assertEqual(response["Retry-After"], "60")

    def test_authenticated_detail_returns_main_fields_and_coupon(self):
        response = self.client.get(f"/api/pedidos/{self.pedido.id}/", HTTP_X_API_KEY=self.raw_api_key)

        self.assertEqual(response.status_code, 200)
        pedido = response.json()["pedido"]
        for field in [
            "id",
            "numero",
            "nome_cliente",
            "telefone",
            "endereco_formatado",
            "latitude",
            "longitude",
            "tipo_coleta",
            "icone_pedido_numero",
            "forma_pagamento",
            "status",
            "valor_frete",
            "total",
            "public_token",
            "criado_em",
            "status_label_contextual",
            "has_coordinates",
            "google_maps_route_url",
            "icone_pedido_url",
            "is_retirada",
            "stage_labels",
        ]:
            self.assertIn(field, pedido)
        self.assertEqual(pedido["nome_cliente"], "Cliente API")
        self.assertIsInstance(pedido["icone_pedido_numero"], int)
        self.assertEqual(pedido["valor_frete"], "10.00")
        self.assertEqual(pedido["total"], "30.00")
        self.assertEqual(pedido["cupom"]["id"], self.cupom.id)
        self.assertEqual(pedido["cupom"]["codigo"], "API10")

    def test_authenticated_detail_can_lookup_by_public_token(self):
        response = self.client.get(
            f"/api/pedidos/token/{self.pedido.public_token}/",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pedido"]["id"], self.pedido.id)

    def test_includes_order_items(self):
        response = self.client.get(f"/api/pedidos/{self.pedido.id}/", HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}")

        item = response.json()["pedido"]["itens"][0]
        self.assertEqual(item["nome_prato_snapshot"], "Marmita API")
        self.assertEqual(item["variacao_nome_snapshot"], "Grande")
        self.assertEqual(item["preco_snapshot"], "35.00")
        self.assertEqual(item["subtotal"], "35.00")

    def test_basic_filters(self):
        Pedido.objects.create(
            nome_cliente="Outro Cliente",
            telefone="64888888888",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("20.00"),
        )
        response = self.client.get(
            "/api/pedidos/?status=em_preparo&tipo_coleta=entrega&telefone=9999",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}",
        )

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["pedidos"][0]["id"], self.pedido.id)

    def test_print_queue_requires_api_key(self):
        response = self.client.get("/api/lista-impressao/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_api_key")

    def test_print_queue_returns_order_entries_in_insertion_order(self):
        PedidoListaImpressao.objects.all().delete()
        first = Pedido.objects.create(
            nome_cliente="Primeiro",
            telefone="64911110000",
            endereco="Rua 1",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("20.00"),
        )
        second = Pedido.objects.create(
            nome_cliente="Segundo",
            telefone="64922220000",
            endereco="Rua 2",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("25.00"),
        )
        first.status = Pedido.Status.EM_PREPARO
        first.save(update_fields=["status"])
        second.status = Pedido.Status.EM_PREPARO
        second.save(update_fields=["status"])

        response = self.client.get("/api/lista-impressao/", HTTP_X_API_KEY=self.raw_api_key)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["next_desde_id"], PedidoListaImpressao.objects.order_by("id").last().id)
        self.assertFalse(payload["has_more"])
        self.assertEqual([item["nome_cliente"] for item in payload["itens"]], ["Primeiro", "Segundo"])
        self.assertEqual(payload["itens"][0]["public_token"], first.public_token)

    def test_print_queue_supports_cursor_and_limit(self):
        PedidoListaImpressao.objects.all().delete()
        first = PedidoListaImpressao.objects.create(
            pedido=self.pedido,
            numero=self.pedido.numero,
            nome_cliente="Primeiro cursor",
            public_token=self.pedido.public_token,
        )
        second = PedidoListaImpressao.objects.create(
            pedido=self.pedido,
            numero=self.pedido.numero,
            nome_cliente="Segundo cursor",
            public_token=self.pedido.public_token,
        )

        response = self.client.get(
            f"/api/lista-impressao/?desde_id={first.id}&limit=1",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_api_key}",
        )

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["next_desde_id"], second.id)
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["itens"][0]["id"], second.id)

    def test_entering_production_registers_print_queue_without_duplicate_on_same_status(self):
        PedidoListaImpressao.objects.all().delete()
        pedido = Pedido.objects.create(
            nome_cliente="Fila Producao",
            telefone="64933330000",
            endereco="Rua Fila",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("22.00"),
        )

        pedido.status = Pedido.Status.EM_PREPARO
        pedido.save(update_fields=["status"])
        pedido.observacao_geral = "Atualizacao sem trocar status"
        pedido.save(update_fields=["observacao_geral"])

        entry = PedidoListaImpressao.objects.get()
        self.assertEqual(entry.nome_cliente, "Fila Producao")
        self.assertEqual(entry.public_token, pedido.public_token)

    def test_returning_to_production_registers_new_print_queue_history_entry(self):
        PedidoListaImpressao.objects.all().delete()
        pedido = Pedido.objects.create(
            nome_cliente="Fila Historico",
            telefone="64944440000",
            endereco="Rua Historico",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("22.00"),
        )

        pedido.status = Pedido.Status.EM_PREPARO
        pedido.save(update_fields=["status"])
        pedido.status = Pedido.Status.NOVO
        pedido.save(update_fields=["status"])
        pedido.status = Pedido.Status.EM_PREPARO
        pedido.save(update_fields=["status"])

        self.assertEqual(PedidoListaImpressao.objects.filter(pedido=pedido).count(), 2)


class PublicFlowCacheTests(TestCase):
    def test_cart_checkout_and_menu_are_not_browser_cached(self):
        for path in ["/", "/carrinho/", "/checkout/"]:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_menu_request_does_not_register_access_on_server_render(self):
        self.client.get("/")
        self.client.get("/")
        self.client.get("/")

        self.assertEqual(AccessEvent.objects.filter(event_type=AccessEvent.EventType.MENU_VIEW).count(), 0)

    def test_repeated_menu_metric_posts_with_same_page_open_id_are_deduplicated(self):
        payload = {
            "event_type": "menu_view",
            "path": "/",
            "metadata": {"origem": "page_open", "page_open_id": "tab-1"},
        }
        for _ in range(3):
            self.client.post("/api/metrics/event/", data=json.dumps(payload), content_type="application/json")

        self.assertEqual(AccessEvent.objects.filter(event_type=AccessEvent.EventType.MENU_VIEW).count(), 1)

    def test_menu_metric_posts_with_different_page_open_ids_are_counted(self):
        for page_open_id in ["tab-1", "tab-2"]:
            self.client.post(
                "/api/metrics/event/",
                data=json.dumps(
                    {
                        "event_type": "menu_view",
                        "path": "/",
                        "metadata": {"origem": "page_open", "page_open_id": page_open_id},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(AccessEvent.objects.filter(event_type=AccessEvent.EventType.MENU_VIEW).count(), 2)


class PedidoDetalheAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="gestor_pedidos",
            password="12345678",
            is_staff=True,
        )

    def test_requires_staff_authentication(self):
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Teste",
            telefone="64999999999",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            distancia_km=Decimal("4.20"),
            valor_frete=Decimal("10.00"),
            total=Decimal("35.00"),
        )
        response = self.client.get(f"/controle/pedidos/{pedido.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_customer_addresses_api_requires_staff_authentication(self):
        response = self.client.get("/controle/api/clientes/enderecos/?telefone=64999999999")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_customer_addresses_api_returns_empty_for_unknown_phone(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/api/clientes/enderecos/?telefone=64999999999")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "cliente": None, "enderecos": []})

    def test_customer_addresses_api_returns_customer_without_addresses(self):
        self.client.force_login(self.staff_user)
        Cliente.objects.create(telefone_normalizado="64999999999", telefone="(64) 99999-9999", nome="Beth")

        response = self.client.get("/controle/api/clientes/enderecos/?telefone=(64) 99999-9999")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["cliente"]["nome"], "Beth")
        self.assertEqual(payload["enderecos"], [])

    def test_customer_addresses_api_returns_normalized_phone_addresses_ordered(self):
        self.client.force_login(self.staff_user)
        cliente = Cliente.objects.create(telefone_normalizado="64999999999", telefone="64999999999", nome="Beth")
        older = EnderecoCliente.objects.create(
            cliente=cliente,
            endereco="Rua Antiga, 10 - Centro, Rio Verde - GO",
            endereco_formatado="Rua Antiga, 10 - Centro, Rio Verde - GO",
            rua="Rua Antiga",
            numero_endereco="10",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            ultimo_uso_em=timezone.now() - timedelta(days=2),
        )
        newer = EnderecoCliente.objects.create(
            cliente=cliente,
            endereco="Rua Nova, 20 - Centro, Rio Verde - GO",
            endereco_formatado="Rua Nova, 20 - Centro, Rio Verde - GO",
            rua="Rua Nova",
            numero_endereco="20",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            complemento="Casa",
            lote_quadra="Lote 3",
            ponto_referencia="Perto da escola",
            latitude=Decimal("-17.0000000"),
            longitude=Decimal("-50.0000000"),
            ultimo_uso_em=timezone.now(),
        )

        response = self.client.get("/controle/api/clientes/enderecos/?telefone=+55 (64) 99999-9999")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["cliente"], {"id": cliente.id, "nome": "Beth", "telefone": "64999999999"})
        self.assertEqual([item["id"] for item in payload["enderecos"]], [newer.id, older.id])
        self.assertEqual(payload["enderecos"][0]["latitude"], "-17.0000000")
        self.assertEqual(payload["enderecos"][0]["longitude"], "-50.0000000")

    def test_draft_order_imports_customer_name_when_phone_is_saved(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        Cliente.objects.create(telefone_normalizado="64999999999", telefone="64999999999", nome="Beth")
        pedido = Pedido.objects.create(
            nome_cliente="Cliente",
            telefone="",
            endereco="Retirada no local",
            endereco_formatado="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.RASCUNHO,
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "telefone", "value": "(64) 99999-9999"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.nome_cliente, "Beth")
        self.assertEqual(response.json()["pedido"]["nome_cliente"], "Beth")

    def test_superuser_can_delete_order_from_context_action(self):
        superuser = get_user_model().objects.create_superuser(username="admin_delete", password="senha")
        self.client.force_login(superuser)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Excluir",
            telefone="64999999999",
            endereco="Rua Excluir",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/excluir/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pedido.objects.filter(id=pedido.id).exists())

    def test_shows_frete_and_distance_audit_information(self):
        self.client.force_login(self.staff_user)
        FaixaFrete.objects.create(
            tipo=FaixaFrete.Tipo.ATE,
            km_limite=Decimal("5.00"),
            valor=Decimal("10.00"),
            ordem=10,
            ativo=True,
        )
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Teste",
            telefone="64999999999",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            distancia_km=Decimal("4.20"),
            valor_frete=Decimal("10.00"),
            total=Decimal("34.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            nome_prato_snapshot="Frango Guisado",
            preco_snapshot=Decimal("24.00"),
            quantidade=1,
        )

        response = self.client.get(f"/controle/pedidos/{pedido.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frete salvo")
        self.assertContains(response, "Distância calculada")
        self.assertEqual(response.context["pedido"], pedido)
        self.assertEqual(response.context["frete_esperado"], Decimal("10.00"))
        self.assertEqual(response.context["itens_subtotal"], Decimal("24.00"))
        self.assertTrue(response.context["frete_confere"])

    def test_orders_admin_keeps_only_active_orders(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        response = self.client.get("/controle/pedidos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Atuais")
        self.assertContains(response, "Adicionar pedido")
        self.assertEqual(response.context["aprovacao_count"], 1)
        self.assertNotContains(response, "Aprovar pedido")
        self.assertNotContains(response, "Pedidos para aprovação")
        self.assertNotIn(pedido, list(response.context["pedidos_ativos"]))

    def test_orders_admin_includes_delivery_lookup_link(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/pedidos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "consultar entrega")
        self.assertContains(response, 'data-open-delivery-lookup')

    def test_approval_orders_admin_shows_approval_queue(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        response = self.client.get("/controle/pedidos-aprovacao/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pedidos para aprovação")
        self.assertContains(response, "Aprovar pedido")
        self.assertContains(response, "data-order-detail-url")
        self.assertNotContains(response, "ped-card-more")
        self.assertIn(pedido, list(response.context["pedidos_aprovacao"]))

        detail_response = self.client.get(
            f"/controle/pedidos/{pedido.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "ped-modal-head")
        self.assertContains(detail_response, "Cliente WhatsApp")
        self.assertContains(detail_response, "Entrega")
        self.assertContains(detail_response, "Total")
        self.assertNotContains(detail_response, "Total recalculado")
        self.assertNotContains(detail_response, "ops-shell")

    def test_approving_order_moves_directly_to_production(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/status/",
            {"status": Pedido.Status.EM_PREPARO},
        )

        self.assertEqual(response.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_PREPARO)
        self.assertIsNotNone(pedido.producao_iniciada_em)

    def test_legacy_approval_to_new_status_is_normalized_to_production(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/status/",
            {"status": Pedido.Status.NOVO},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_PREPARO)
        self.assertIsNotNone(pedido.producao_iniciada_em)

    def test_active_order_advances_through_waiting_driver_step(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )
        production_started_at = pedido.producao_iniciada_em

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/status/",
            {"status": Pedido.Status.AGUARDANDO_ENTREGADOR},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_ENTREGADOR)
        self.assertEqual(pedido.producao_iniciada_em, production_started_at)

        payload_response = self.client.get("/controle/api/pedidos-admin/")
        self.assertNotEqual(payload_response.json()["pedidos"][0]["tempo_producao"], "--")

    def test_production_timer_is_preserved_when_returning_steps(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )
        production_started_at = pedido.producao_iniciada_em

        for status in [
            Pedido.Status.AGUARDANDO_ENTREGADOR,
            Pedido.Status.EM_PREPARO,
            Pedido.Status.NOVO,
            Pedido.Status.EM_PREPARO,
        ]:
            response = self.client.post(
                f"/controle/pedido/{pedido.id}/status/",
                {"status": status},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200)
            pedido.refresh_from_db()
            self.assertEqual(pedido.producao_iniciada_em, production_started_at)

    def test_only_manager_can_update_order_payment(self):
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        self.client.force_login(self.staff_user)
        response = self.client.post(
            f"/controle/pedido/{pedido.id}/pagamento/",
            {"forma_pagamento": Pedido.FormaPagamento.DINHEIRO},
        )
        self.assertEqual(response.status_code, 400)

        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        response = self.client.post(
            f"/controle/pedido/{pedido.id}/pagamento/",
            {"forma_pagamento": Pedido.FormaPagamento.DINHEIRO},
        )
        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.DINHEIRO)

    def test_manager_can_update_simple_order_fields(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        detail_response = self.client.get(
            f"/controle/pedidos/{pedido.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertContains(detail_response, "data-inline-edit")
        self.assertContains(detail_response, "data-field=\"nome_cliente\"")
        self.assertContains(detail_response, "data-field=\"telefone\"")
        self.assertContains(detail_response, "data-field=\"forma_pagamento\"")
        self.assertContains(detail_response, "data-param=\"forma_pagamento\"")
        self.assertContains(detail_response, "data-field=\"enviar_talheres\"")
        self.assertContains(detail_response, "data-field=\"canal\"")
        self.assertContains(detail_response, "data-field=\"tipo_coleta\"")
        self.assertContains(detail_response, "data-field=\"observacao_geral\"")
        self.assertContains(detail_response, "data-open-delivery-editor")
        self.assertContains(detail_response, "data-delivery-editor-template")
        self.assertNotContains(detail_response, "data-toggle-order-editor")

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "nome_cliente", "value": "Cliente Editado"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "telefone", "value": "6411112222"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "enviar_talheres", "value": "nao"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "observacao_geral", "value": "Sem cebola"},
        )
        self.assertEqual(response.status_code, 200)

        pedido.refresh_from_db()
        self.assertEqual(pedido.nome_cliente, "Cliente Editado")
        self.assertEqual(pedido.telefone, "6411112222")
        self.assertFalse(pedido.enviar_talheres)
        self.assertEqual(pedido.observacao_geral, "Sem cebola")

    def test_manager_can_update_order_delivery_without_coordinates(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            valor_frete=Decimal("12.00"),
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/entrega/",
            {
                "rua": "Rua Nova",
                "numero": "55",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "complemento": "Casa",
                "lote_quadra": "Lote 2",
                "ponto_referencia": "Perto da praca",
                "endereco_formatado": "Rua Nova, 55 - Centro, Rio Verde - GO",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["frete_recalculado"])
        pedido.refresh_from_db()
        self.assertEqual(pedido.endereco, "Rua Nova, 55 - Centro, Rio Verde - GO")
        self.assertEqual(pedido.valor_frete, Decimal("12.00"))
        self.assertEqual(pedido.complemento, "Casa")
        self.assertEqual(pedido.tipo_coleta, Pedido.TipoColeta.ENTREGA)

    def test_manager_can_change_order_to_pickup_and_zero_delivery(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            rua="Rua Teste",
            numero_endereco="100",
            bairro="Centro",
            latitude=Decimal("-17.7700000"),
            longitude=Decimal("-50.9000000"),
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.SAIU_ENTREGA,
            valor_frete=Decimal("12.00"),
            total=Decimal("35.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            nome_prato_snapshot="Prato",
            preco_snapshot=Decimal("23.00"),
            quantidade=1,
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "tipo_coleta", "value": Pedido.TipoColeta.RETIRADA},
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.tipo_coleta, Pedido.TipoColeta.RETIRADA)
        self.assertEqual(pedido.endereco, "Retirada no local")
        self.assertEqual(pedido.valor_frete, Decimal("0.00"))
        self.assertEqual(pedido.distancia_km, Decimal("0.00"))
        self.assertIsNone(pedido.latitude)
        self.assertIsNone(pedido.longitude)
        self.assertEqual(pedido.status, Pedido.Status.FINALIZADO)
        self.assertEqual(pedido.total, Decimal("23.00"))

    def test_delivery_address_change_sets_order_to_delivery(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_ENTREGADOR,
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/entrega/",
            {
                "rua": "Rua Nova",
                "numero": "55",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "endereco_formatado": "Rua Nova, 55 - Centro, Rio Verde - GO",
            },
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.tipo_coleta, Pedido.TipoColeta.ENTREGA)
        self.assertEqual(pedido.endereco, "Rua Nova, 55 - Centro, Rio Verde - GO")

    def test_manager_can_replace_order_items_and_recalculate_total(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), ativo=True)
        adicional = Adicional.objects.create(nome="Bacon", preco=Decimal("9.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            valor_frete=Decimal("10.00"),
            total=Decimal("35.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            nome_prato_snapshot=prato.nome,
            preco_snapshot=Decimal("25.00"),
            quantidade=1,
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/itens/",
            {
                "itens_payload": json.dumps(
                    [
                        {"tipo": "prato", "item_id": prato.id, "quantidade": 2},
                        {"tipo": "adicional", "item_id": adicional.id, "quantidade": 1},
                    ]
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.itens.count(), 2)
        self.assertEqual(pedido.total_sem_desconto, Decimal("69.00"))
        self.assertEqual(pedido.total, Decimal("69.00"))

    def test_manager_can_mark_order_as_ifood_and_reprice_items(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), preco_ifood=Decimal("32.00"), ativo=True)
        bebida = Bebida.objects.create(nome="Refrigerante", preco=Decimal("6.00"), preco_ifood=Decimal("8.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente iFood",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            valor_frete=Decimal("0.00"),
            total=Decimal("31.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            nome_prato_snapshot=prato.nome,
            preco_snapshot=Decimal("25.00"),
            quantidade=1,
        )
        ItemPedido.objects.create(
            pedido=pedido,
            bebida=bebida,
            nome_prato_snapshot=bebida.nome,
            preco_snapshot=Decimal("6.00"),
            quantidade=1,
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "ifood", "value": "sim"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertTrue(pedido.ifood)
        self.assertEqual(pedido.itens.get(prato=prato).preco_snapshot, Decimal("32.00"))
        self.assertEqual(pedido.itens.get(bebida=bebida).preco_snapshot, Decimal("8.00"))
        self.assertEqual(pedido.total, Decimal("40.00"))
        self.assertEqual(response.json()["pedido"]["ifood"], "sim")
        self.assertEqual(response.json()["pedido"]["ifood_label"], "iFood")
        self.assertEqual(response.json()["pedido"]["canal"], "ifood")
        self.assertEqual(response.json()["pedido"]["canal_label"], "iFood")

    def test_manager_can_change_order_channel_and_reprice_items(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(
            nome="Carreteiro",
            preco=Decimal("25.00"),
            preco_balcao=Decimal("24.00"),
            preco_site=Decimal("27.00"),
            preco_ifood=Decimal("32.00"),
            ativo=True,
        )
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Site",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            canal=Pedido.Canal.BALCAO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            valor_frete=Decimal("0.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            nome_prato_snapshot=prato.nome,
            preco_snapshot=Decimal("24.00"),
            quantidade=1,
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/dados/",
            {"field": "canal", "value": "site"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.canal, Pedido.Canal.SITE)
        self.assertFalse(pedido.ifood)
        self.assertEqual(pedido.itens.get(prato=prato).preco_snapshot, Decimal("27.00"))
        self.assertEqual(pedido.total, Decimal("27.00"))

    def test_ifood_shortcut_creates_draft_order_with_ifood_channel(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        response = self.client.get("/controle/pedidos/novo/?canal=ifood", HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        pedido = Pedido.objects.latest("id")
        self.assertEqual(pedido.canal, Pedido.Canal.IFOOD)
        self.assertTrue(pedido.ifood)
        self.assertContains(response, 'data-field="canal"')
        self.assertContains(response, 'data-value="ifood"')

    def test_ifood_order_uses_ifood_price_when_replacing_items(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), preco_ifood=Decimal("32.00"), ativo=True)
        adicional = Adicional.objects.create(nome="Bacon", preco=Decimal("9.00"), preco_ifood=Decimal("12.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente iFood",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            ifood=True,
            valor_frete=Decimal("0.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/itens/",
            {
                "itens_payload": json.dumps(
                    [
                        {"tipo": "prato", "item_id": prato.id, "quantidade": 1},
                        {"tipo": "adicional", "item_id": adicional.id, "quantidade": 2},
                    ]
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.itens.get(prato=prato).preco_snapshot, Decimal("32.00"))
        self.assertEqual(pedido.itens.get(adicional=adicional).preco_snapshot, Decimal("12.00"))
        self.assertEqual(pedido.total, Decimal("56.00"))

    def test_manager_can_apply_and_remove_coupon_from_order_modal(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), ativo=True)
        Cupom.objects.create(
            codigo="OFF10",
            tipo_desconto=Cupom.TipoDesconto.VALOR_FIXO,
            valor=Decimal("10.00"),
            ativo=True,
        )
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            valor_frete=Decimal("5.00"),
            total=Decimal("30.00"),
        )
        ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            nome_prato_snapshot=prato.nome,
            preco_snapshot=Decimal("25.00"),
            quantidade=1,
        )

        detail_response = self.client.get(
            f"/controle/pedidos/{pedido.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertContains(detail_response, "data-coupon-form")

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/cupom/",
            {"cupom_codigo": "off10"},
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.cupom_codigo, "OFF10")
        self.assertEqual(pedido.cupom_desconto, Decimal("10.00"))
        self.assertEqual(pedido.total, Decimal("20.00"))

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/cupom/",
            {"cupom_codigo": ""},
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.cupom_codigo, "")
        self.assertEqual(pedido.cupom_desconto, Decimal("0.00"))
        self.assertEqual(pedido.total, Decimal("30.00"))

    def test_invalid_coupon_returns_bad_request_for_order_modal(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente WhatsApp",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("30.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/cupom/",
            {"cupom_codigo": "NAOEXISTE"},
        )

        self.assertEqual(response.status_code, 400)

    def test_staff_can_load_editor_catalog(self):
        self.client.force_login(self.staff_user)
        Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), preco_ifood=Decimal("32.00"), ativo=True)

        response = self.client.get("/controle/api/catalogo-editor/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["nome"], "Carreteiro")
        self.assertEqual(response.json()["items"][0]["preco_ifood"], "32.00")

    def test_new_order_modal_uses_detail_modal_context(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)

        response = self.client.get(
            "/controle/pedidos/novo/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-new-order-finalize-form")
        self.assertContains(response, "data-items-editor")
        self.assertContains(response, "/controle/api/catalogo-editor/")
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.status, Pedido.Status.RASCUNHO)

    def test_manager_can_finalize_new_order_from_detail_modal_context(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Balcao",
            telefone="64999999999",
            endereco="Retirada no local",
            endereco_formatado="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.RASCUNHO,
        )
        create_order_items_from_payload(
            pedido,
            [
                {"tipo": "prato", "item_id": prato.id, "quantidade": 2},
            ],
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/finalizar-novo/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.nome_cliente, "Cliente Balcao")
        self.assertEqual(pedido.status, Pedido.Status.EM_PREPARO)
        self.assertIsNotNone(pedido.producao_iniciada_em)
        self.assertEqual(pedido.total, Decimal("50.00"))
        self.assertEqual(response.json()["detail_url"], f"/controle/pedidos/{pedido.id}/")

    def test_sync_customer_from_order_reuses_phone(self):
        first = Pedido.objects.create(
            nome_cliente="Maria",
            telefone="(64) 99999-0000",
            rua="Rua 1",
            numero_endereco="10",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua 1, 10 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("25.00"),
        )
        second = Pedido.objects.create(
            nome_cliente="Maria Silva",
            telefone="64 99999-0000",
            rua="Rua 2",
            numero_endereco="20",
            bairro="Centro",
            cidade="Rio Verde",
            estado="GO",
            endereco="Rua 2, 20 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("30.00"),
        )

        first_customer = sync_customer_from_order(first)
        second_customer = sync_customer_from_order(second)

        self.assertEqual(first_customer.id, second_customer.id)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Cliente.objects.get().pedidos.count(), 2)
        self.assertEqual(EnderecoCliente.objects.count(), 2)
        self.assertEqual(second.cliente_id, first_customer.id)

    def test_customers_admin_lists_customer_and_profile(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Perfil",
            telefone="64988887777",
            endereco="Rua Perfil, 50 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("40.00"),
        )
        cliente = sync_customer_from_order(pedido)

        list_response = self.client.get("/controle/clientes/")
        detail_response = self.client.get(f"/controle/clientes/{cliente.id}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Cliente Perfil")
        self.assertContains(list_response, "64988887777")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, pedido.public_token)
        self.assertContains(detail_response, "Rua Perfil")

    def test_manager_can_edit_customer_name_manually(self):
        self.client.force_login(self.staff_user)
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        pedido = Pedido.objects.create(
            nome_cliente="Nome Pedido",
            telefone="64977776666",
            endereco="Retirada no local",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("20.00"),
        )
        cliente = sync_customer_from_order(pedido)

        response = self.client.post(f"/controle/clientes/{cliente.id}/", {"nome": "Nome Manual"})

        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nome, "Nome Manual")
        self.assertTrue(cliente.nome_editado_manualmente)

    def test_order_without_phone_inherits_customer_from_known_token(self):
        previous = Pedido.objects.create(
            nome_cliente="Cliente Token",
            telefone="64966665555",
            endereco="Rua Token, 10 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("22.00"),
        )
        cliente = sync_customer_from_order(previous)
        current = Pedido.objects.create(
            nome_cliente="Cliente Sem Telefone",
            telefone="",
            endereco="Retirada no local",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("18.00"),
        )

        inherited = inherit_customer_from_known_tokens(current, [previous.public_token])

        current.refresh_from_db()
        self.assertEqual(inherited.id, cliente.id)
        self.assertEqual(current.cliente_id, cliente.id)
        self.assertEqual(current.telefone, cliente.telefone)
        self.assertEqual(ClienteTokenConflito.objects.count(), 0)

    def test_order_with_placeholder_name_inherits_customer_name_from_phone(self):
        previous = Pedido.objects.create(
            nome_cliente="Beth",
            telefone="64999168848",
            endereco="Rua Beth, 10 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("22.00"),
        )
        cliente = sync_customer_from_order(previous)
        current = Pedido.objects.create(
            nome_cliente="Cliente",
            telefone="64999168848",
            endereco="Retirada no local",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("18.00"),
        )

        sync_customer_from_order(current)

        current.refresh_from_db()
        self.assertEqual(current.cliente_id, cliente.id)
        self.assertEqual(current.nome_cliente, "Beth")

    def test_order_without_phone_inherits_customer_from_history_cookie(self):
        previous = Pedido.objects.create(
            nome_cliente="Cliente Cookie",
            telefone="64977778888",
            endereco="Rua Cookie, 10 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("22.00"),
        )
        cliente = sync_customer_from_order(previous)
        config = ConfiguracaoEntrega.get_solo()
        config.whatsapp_numero = "5564999999999"
        config.save()
        prato = Prato.objects.create(nome="Carreteiro", preco=Decimal("24.90"), ativo=True)
        self.client.cookies[ORDER_HISTORY_COOKIE] = json.dumps([{"token": previous.public_token}])

        response = self.client.post(
            "/pedido/retirada/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % prato.id,
                "nome_cliente": "Cliente Sem Telefone",
                "observacao_geral": "",
                "enviar_talheres": "sim",
            },
        )

        self.assertEqual(response.status_code, 302)
        current = Pedido.objects.order_by("-id").first()
        self.assertEqual(current.cliente_id, cliente.id)
        self.assertEqual(current.telefone, cliente.telefone)

    def test_order_without_phone_registers_conflict_for_multiple_token_customers(self):
        first = Pedido.objects.create(
            nome_cliente="Cliente Um",
            telefone="64911110000",
            endereco="Rua Um, 1 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("22.00"),
        )
        second = Pedido.objects.create(
            nome_cliente="Cliente Dois",
            telefone="64922220000",
            endereco="Rua Dois, 2 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("25.00"),
        )
        first_customer = sync_customer_from_order(first)
        second_customer = sync_customer_from_order(second)
        current = Pedido.objects.create(
            nome_cliente="Cliente Sem Telefone",
            telefone="",
            endereco="Retirada no local",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("18.00"),
        )

        result = inherit_customer_from_known_tokens(current, [first.public_token, second.public_token])

        current.refresh_from_db()
        conflito = ClienteTokenConflito.objects.get()
        self.assertIsNone(result)
        self.assertIsNone(current.cliente_id)
        self.assertEqual(set(conflito.clientes.values_list("id", flat=True)), {first_customer.id, second_customer.id})

    def test_customer_conflicts_page_lists_open_conflicts(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Pedido Conflito",
            telefone="",
            endereco="Retirada no local",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("18.00"),
        )
        cliente = Cliente.objects.create(telefone_normalizado="64912340000", telefone="64912340000", nome="Cliente Conflito")
        conflito = ClienteTokenConflito.objects.create(pedido=pedido, tokens=["abc"])
        conflito.clientes.add(cliente)

        response = self.client.get("/controle/clientes/conflitos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Pedido #{pedido.numero}")
        self.assertContains(response, "Cliente Conflito")

    def test_completed_orders_admin_shows_closed_orders(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Entregue",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("35.00"),
        )

        response = self.client.get("/controle/pedidos-concluidos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Concluídos")
        self.assertIn(pedido, list(response.context["pedidos_concluidos"]))

    def test_orders_admin_api_returns_only_active_orders(self):
        self.client.force_login(self.staff_user)
        active = Pedido.objects.create(
            nome_cliente="Cliente Ativo",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.NOVO,
            total=Decimal("35.00"),
        )
        Pedido.objects.create(
            nome_cliente="Cliente Finalizado",
            telefone="64999999999",
            endereco="Rua Teste, 101 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("40.00"),
        )

        response = self.client.get("/controle/api/pedidos-admin/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aprovacao_count"], 0)
        self.assertEqual(payload["pedidos_badge"], 1)
        self.assertEqual([pedido["id"] for pedido in payload["pedidos"]], [active.id])

    def test_kitchen_api_returns_item_type_counts(self):
        self.client.force_login(self.staff_user)
        prato = Prato.objects.create(nome="Marmita", preco=Decimal("25.00"), ativo=True)
        adicional = Adicional.objects.create(nome="Farofa", preco=Decimal("4.00"), ativo=True)
        bebida = Bebida.objects.create(nome="Suco", preco=Decimal("7.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Contadores",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )
        ItemPedido.objects.create(pedido=pedido, prato=prato, nome_prato_snapshot="Marmita", preco_snapshot=Decimal("25.00"), quantidade=2)
        ItemPedido.objects.create(pedido=pedido, adicional=adicional, nome_prato_snapshot="Farofa", preco_snapshot=Decimal("4.00"), quantidade=3)
        ItemPedido.objects.create(pedido=pedido, bebida=bebida, nome_prato_snapshot="Suco", preco_snapshot=Decimal("7.00"), quantidade=4)

        payload = self.client.get("/controle/api/pedidos/").json()
        operacao_payload = self.client.get("/controle/api/operacao/").json()

        self.assertEqual(payload["pedidos"][0]["item_type_counts"], {"pratos": 2, "adicionais": 3, "bebidas": 4})
        self.assertEqual(operacao_payload["pedidos_cards"][0]["item_type_counts"], {"pratos": 2, "adicionais": 3, "bebidas": 4})

    def test_order_apis_display_created_time_in_local_timezone(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Ativo",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.NOVO,
            total=Decimal("35.00"),
        )
        Pedido.objects.filter(pk=pedido.pk).update(
            criado_em=datetime.fromisoformat("2026-05-14T12:00:00+00:00")
        )

        admin_payload = self.client.get("/controle/api/pedidos-admin/").json()
        cozinha_payload = self.client.get("/controle/api/pedidos/").json()

        self.assertEqual(admin_payload["pedidos"][0]["criado_em"], "14/05, 09:00")
        self.assertEqual(cozinha_payload["pedidos"][0]["horario"], "09:00")

    def test_active_order_can_toggle_delivery_marker(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Ativo",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )

        page_response = self.client.get("/controle/pedidos/")
        self.assertContains(page_response, "Entregador solicitado")
        self.assertContains(page_response, "Copiar pedido")
        self.assertContains(page_response, "Copiar endereço")
        self.assertContains(page_response, f"/controle/api/pedido/{pedido.id}/copias/")

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/entregador/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertTrue(pedido.entregador_solicitado)
        payload = self.client.get("/controle/api/pedidos-admin/").json()
        self.assertTrue(payload["pedidos"][0]["entregador_solicitado"])
        self.assertEqual(payload["pedidos"][0]["copy_url"], f"/controle/api/pedido/{pedido.id}/copias/")
        self.assertEqual(payload["pedidos"][0]["icone_url"], pedido.icone_pedido_url)

    def test_kitchen_card_displays_discreet_item_type_counts(self):
        self.client.force_login(self.staff_user)
        prato = Prato.objects.create(nome="Marmita", preco=Decimal("25.00"), ativo=True)
        adicional = Adicional.objects.create(nome="Farofa", preco=Decimal("4.00"), ativo=True)
        bebida = Bebida.objects.create(nome="Suco", preco=Decimal("7.00"), ativo=True)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Contadores",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )
        ItemPedido.objects.create(pedido=pedido, prato=prato, nome_prato_snapshot="Marmita", preco_snapshot=Decimal("25.00"), quantidade=2)
        ItemPedido.objects.create(pedido=pedido, adicional=adicional, nome_prato_snapshot="Farofa", preco_snapshot=Decimal("4.00"), quantidade=3)
        ItemPedido.objects.create(pedido=pedido, bebida=bebida, nome_prato_snapshot="Suco", preco_snapshot=Decimal("7.00"), quantidade=4)

        response = self.client.get("/controle/operacao/")

        self.assertContains(response, 'class="kitchen-type-counts"')
        self.assertContains(response, 'title="Pratos"')
        self.assertContains(response, 'title="Adicionais"')
        self.assertContains(response, 'title="Bebidas"')
        self.assertContains(response, "2")
        self.assertContains(response, "3")
        self.assertContains(response, "4")

    def test_order_icons_are_assigned_by_order_number_sequence(self):
        first = Pedido.objects.create(
            nome_cliente="Cliente Um",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )
        second = Pedido.objects.create(
            nome_cliente="Cliente Dois",
            telefone="64999999999",
            endereco="Rua Teste, 101 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("40.00"),
        )

        self.assertEqual(first.icone_pedido, Pedido.icon_path_for_number(first.numero))
        self.assertEqual(second.icone_pedido, Pedido.icon_path_for_number(second.numero))
        self.assertNotEqual(first.icone_pedido, second.icone_pedido)
        self.assertTrue(first.icone_pedido_url.startswith("/static/img/Icones_pedidos/"))

    def test_order_copy_api_returns_customer_and_delivery_texts(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Ativo",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            complemento="Casa 2",
            ponto_referencia="Portao azul",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )

        response = self.client.get(f"/controle/api/pedido/{pedido.id}/copias/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(f"Pedido #{pedido.numero}", payload["cliente"])
        self.assertIn("*Cliente:* Cliente Ativo", payload["cliente"])
        self.assertIn(f"Pedido #{pedido.numero} - Cliente Ativo", payload["entregador"])
        self.assertIn("Endereço: Rua Teste, 100 - Centro, Rio Verde - GO", payload["entregador"])
        self.assertIn("Complemento: Casa 2", payload["entregador"])
        self.assertNotIn("Telefone", payload["entregador"])

    def test_order_detail_modal_has_discreet_label_print_queue_button(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Botao",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("35.00"),
        )

        response = self.client.get(
            f"/controle/pedidos/{pedido.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-print-queue-form")
        self.assertContains(response, "Imprimir rotulo")
        self.assertContains(response, f"/controle/api/pedido/{pedido.id}/lista-impressao/")

    def test_manual_print_queue_button_registers_order(self):
        self.client.force_login(self.staff_user)
        PedidoListaImpressao.objects.all().delete()
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Manual",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )

        response = self.client.post(f"/controle/api/pedido/{pedido.id}/lista-impressao/")

        self.assertEqual(response.status_code, 200)
        entry = PedidoListaImpressao.objects.get()
        self.assertEqual(response.json()["id"], entry.id)
        self.assertEqual(entry.nome_cliente, "Cliente Manual")
        self.assertEqual(entry.public_token, pedido.public_token)

    def test_approval_orders_admin_api_returns_realtime_queue(self):
        self.client.force_login(self.staff_user)
        approval = Pedido.objects.create(
            nome_cliente="Cliente Aprovacao",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.AGUARDANDO_APROVACAO,
            total=Decimal("35.00"),
        )
        Pedido.objects.create(
            nome_cliente="Cliente Ativo",
            telefone="64999999999",
            endereco="Rua Teste, 101 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("40.00"),
        )

        response = self.client.get("/controle/api/pedidos-aprovacao/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["aprovacao_count"], 1)
        self.assertEqual(payload["pedidos_badge"], 1)
        self.assertEqual([pedido["id"] for pedido in payload["pedidos"]], [approval.id])

    def test_active_order_api_uses_pickup_stage_labels(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Retirada",
            telefone="",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_ENTREGADOR,
            total=Decimal("35.00"),
        )

        response = self.client.get("/controle/api/pedidos-admin/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["pedidos"][0]
        self.assertEqual(payload["id"], pedido.id)
        self.assertEqual(payload["tipo_coleta"], Pedido.TipoColeta.RETIRADA)
        self.assertEqual(payload["status_label"], "Aguardando coleta")
        self.assertIn(
            {"status": Pedido.Status.AGUARDANDO_ENTREGADOR, "number": "3", "label": "Aguardando coleta"},
            payload["stage_labels"],
        )
        self.assertIn(
            {"status": Pedido.Status.FINALIZADO, "number": "4", "label": "Finalizado"},
            payload["stage_labels"],
        )
        self.assertNotIn(Pedido.Status.SAIU_ENTREGA, [stage["status"] for stage in payload["stage_labels"]])

    def test_pickup_order_skips_delivery_stage_when_advanced(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Retirada",
            telefone="",
            endereco="Retirada no local",
            tipo_coleta=Pedido.TipoColeta.RETIRADA,
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.AGUARDANDO_ENTREGADOR,
            total=Decimal("35.00"),
        )

        response = self.client.post(
            f"/controle/pedido/{pedido.id}/status/",
            {"status": Pedido.Status.SAIU_ENTREGA},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.FINALIZADO)
        self.assertEqual(response.json()["status"], "Finalizado")

    def test_completed_orders_admin_api_returns_closed_orders(self):
        self.client.force_login(self.staff_user)
        done = Pedido.objects.create(
            nome_cliente="Cliente Entregue",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("35.00"),
        )
        canceled = Pedido.objects.create(
            nome_cliente="Cliente Cancelado",
            telefone="64999999999",
            endereco="Rua Teste, 101 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.CANCELADO,
            total=Decimal("40.00"),
        )

        response = self.client.get("/controle/api/pedidos-concluidos/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["concluidos_count"], 1)
        self.assertEqual(payload["cancelados_count"], 1)
        self.assertEqual([pedido["id"] for pedido in payload["pedidos_concluidos"]], [done.id])
        self.assertEqual([pedido["id"] for pedido in payload["pedidos_cancelados"]], [canceled.id])

    def test_completed_orders_page_opens_modal_and_shows_only_back_action(self):
        self.client.force_login(self.staff_user)
        done = Pedido.objects.create(
            nome_cliente="Cliente Entregue",
            telefone="64999999999",
            endereco="Rua Teste, 100 - Centro, Rio Verde - GO",
            forma_pagamento=Pedido.FormaPagamento.PIX,
            status=Pedido.Status.FINALIZADO,
            total=Decimal("35.00"),
        )

        response = self.client.get("/controle/pedidos-concluidos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-order-detail-url="/controle/pedidos/{done.id}/"')
        self.assertContains(response, "data-pedido-detail-modal")
        self.assertContains(response, "pedido_detail_modal.js")
        self.assertContains(response, "Voltar etapa")
        self.assertContains(response, 'name="status" value="saiu_entrega"')
        self.assertNotContains(response, "ped-card-more")
        self.assertNotContains(response, "Detalhes")


class AjustesAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="ajustes_staff",
            password="12345678",
            is_staff=True,
        )
        FaixaFrete.objects.bulk_create(
            [
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("5.00"), valor=Decimal("10.00"), ordem=10, ativo=True),
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("10.00"), valor=Decimal("20.00"), ordem=20, ativo=True),
            ]
        )

    def test_requires_staff_authentication(self):
        response = self.client.get("/controle/ajustes/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_general_tab_displays_operation_hours(self):
        self.client.force_login(self.staff_user)
        config = ConfiguracaoEntrega.get_solo()
        config.horario_abertura = time(10, 30)
        config.horario_fechamento = time(14, 45)
        config.save()

        response = self.client.get("/controle/ajustes/?aba=geral")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Horário de funcionamento")
        self.assertContains(response, 'value="10:30"')
        self.assertContains(response, 'value="14:45"')

    def test_api_tab_displays_read_only_order_endpoints(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/ajustes/?aba=api")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API somente leitura")
        self.assertContains(response, "GET /api/pedidos/")
        self.assertContains(response, "GET /api/pedidos/&lt;id&gt;/")
        self.assertContains(response, "Authorization: Bearer SUA_CHAVE")
        self.assertContains(response, "?status=em_preparo")

    def test_print_queue_tab_displays_history_and_endpoint(self):
        self.client.force_login(self.staff_user)
        pedido = Pedido.objects.create(
            nome_cliente="Cliente Impressao",
            telefone="64955550000",
            endereco="Rua Impressao",
            forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
            status=Pedido.Status.EM_PREPARO,
            total=Decimal("20.00"),
        )

        response = self.client.get("/controle/ajustes/?aba=lista_impressao")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historico da lista de rotulos")
        self.assertContains(response, "GET /api/lista-impressao/")
        self.assertContains(response, "GET /api/pedidos/token/&lt;public_token&gt;/")
        self.assertContains(response, "Cliente Impressao")
        self.assertContains(response, pedido.public_token)

    def test_manager_can_create_and_delete_api_key_from_settings(self):
        gerente_group, _created = Group.objects.get_or_create(name="Gerente")
        self.staff_user.groups.add(gerente_group)
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=api",
            {"action": "create_api_key", "nome": "Integracao teste"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chave criada. Copie agora: pd_")
        api_key = PedidoApiKey.objects.get(nome="Integracao teste")
        self.assertEqual(api_key.criado_por, self.staff_user)
        self.assertNotIn("pd_", api_key.chave_hash)

        response = self.client.post(
            "/controle/ajustes/?aba=api",
            {"action": "delete_api_key", "api_key_id": api_key.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PedidoApiKey.objects.filter(id=api_key.id).exists())

    def test_non_manager_cannot_create_api_key_from_settings(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=api",
            {"action": "create_api_key", "nome": "Sem permissao"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario sem permissao para criar chaves da API.")
        self.assertFalse(PedidoApiKey.objects.filter(nome="Sem permissao").exists())

    def test_general_settings_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=geral",
            {
                "action": "save_geral",
                "horario_abertura": "09:00",
                "horario_fechamento": "15:30",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("aba=geral", response.url)
        config = ConfiguracaoEntrega.get_solo()
        self.assertEqual(config.horario_abertura.strftime("%H:%M"), "09:00")
        self.assertEqual(config.horario_fechamento.strftime("%H:%M"), "15:30")

    def test_saves_origin_and_faixa_updates(self):
        self.client.force_login(self.staff_user)
        faixa = FaixaFrete.objects.order_by("ordem").first()

        response = self.client.post(
            "/controle/ajustes/",
            {
                "action": "save_frete",
                "origem_endereco": "Rua A, 10 - Centro, Rio Verde - GO",
                "origem_latitude": "-17.8000000",
                "origem_longitude": "-50.9100000",
                "faixa_row_key": [f"existing-{faixa.id}", "new-1"],
                "faixa_id": [str(faixa.id), ""],
                "faixa_tipo": [FaixaFrete.Tipo.ATE, FaixaFrete.Tipo.ACIMA],
                "faixa_km_limite": ["6.00", "12.00"],
                "faixa_valor": ["12.50", "28.00"],
                "faixa_ordem": ["10", "30"],
                "faixa_ativo": [f"existing-{faixa.id}", "new-1"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.url)

        config = ConfiguracaoEntrega.get_solo()
        self.assertEqual(config.origem_endereco, "Rua A, 10 - Centro, Rio Verde - GO")
        self.assertEqual(config.origem_latitude, Decimal("-17.8000000"))
        self.assertEqual(config.origem_longitude, Decimal("-50.9100000"))

        faixa.refresh_from_db()
        self.assertEqual(faixa.km_limite, Decimal("6.00"))
        self.assertEqual(faixa.valor, Decimal("12.50"))
        self.assertTrue(FaixaFrete.objects.filter(tipo=FaixaFrete.Tipo.ACIMA, km_limite=Decimal("12.00")).exists())

    def test_save_requires_confirmed_origin_coordinates(self):
        self.client.force_login(self.staff_user)
        faixa = FaixaFrete.objects.order_by("ordem").first()

        response = self.client.post(
            "/controle/ajustes/",
            {
                "action": "save_frete",
                "origem_endereco": "Rua A, 10 - Centro, Rio Verde - GO",
                "origem_latitude": "",
                "origem_longitude": "",
                "faixa_row_key": [f"existing-{faixa.id}"],
                "faixa_id": [str(faixa.id)],
                "faixa_tipo": [FaixaFrete.Tipo.ATE],
                "faixa_km_limite": ["5.00"],
                "faixa_valor": ["10.00"],
                "faixa_ordem": ["10"],
                "faixa_ativo": [f"existing-{faixa.id}"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirme a origem no mapa antes de salvar")
        config = ConfiguracaoEntrega.objects.order_by("pk").first()
        self.assertIsNone(config.origem_latitude)
        self.assertIsNone(config.origem_longitude)

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 5870.0))
    def test_preview_uses_current_form_values(self, _mock_route):
        self.client.force_login(self.staff_user)
        faixas = list(FaixaFrete.objects.order_by("ordem"))

        response = self.client.post(
            "/controle/ajustes/",
            {
                "action": "test_frete",
                "origem_endereco": "Rua B, 22 - Centro, Rio Verde - GO",
                "origem_latitude": "-17.8010000",
                "origem_longitude": "-50.9110000",
                "destino_teste": "Rua Teste, 50 - Centro, Rio Verde - GO",
                "destino_teste_lat": "-17.7700000",
                "destino_teste_lng": "-50.9000000",
                "destino_teste_label": "Rua Teste, Centro, Rio Verde - GO",
                "destino_teste_tipo": "street_address",
                "destino_teste_precision": "exact",
                "faixa_row_key": [f"existing-{faixas[0].id}", f"existing-{faixas[1].id}"],
                "faixa_id": [str(faixas[0].id), str(faixas[1].id)],
                "faixa_tipo": [FaixaFrete.Tipo.ATE, FaixaFrete.Tipo.ATE],
                "faixa_km_limite": ["5.00", "10.00"],
                "faixa_valor": ["11.00", "21.00"],
                "faixa_ordem": ["10", "20"],
                "faixa_ativo": [f"existing-{faixas[0].id}", f"existing-{faixas[1].id}"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frete calculado")
        preview = response.context["preview"]
        self.assertEqual(preview["distance_km"], 5.87)
        self.assertEqual(preview["frete_valor"], Decimal("21.00"))
        self.assertIn("10,00 km", preview["faixa_label"])
        self.assertTrue(preview["origem_nao_salva"])
        self.assertContains(response, "Este teste usou uma origem ainda não salva")

    @override_settings(GOOGLE_MAPS_API_KEY="abcdef1234567890", GOOGLE_MAPS_LANGUAGE="pt-BR", GOOGLE_MAPS_REGION="BR")
    def test_google_tab_displays_provider_status(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/ajustes/?aba=google")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google Maps")
        self.assertContains(response, "abcdef...7890")
        self.assertContains(response, "Maps JavaScript API")
        self.assertContains(response, "Geocoding API")

    def test_google_settings_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=google",
            {
                "action": "save_google",
                "google_maps_api_key": "chave-google-123",
                "google_maps_language": "pt-BR",
                "google_maps_region": "BR",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("aba=google", response.url)

        config = ConfiguracaoEntrega.get_solo()
        self.assertEqual(config.google_maps_api_key, "chave-google-123")
        self.assertEqual(config.google_maps_language, "pt-BR")
        self.assertEqual(config.google_maps_region, "BR")

    def test_whatsapp_number_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=whatsapp",
            {
                "action": "save_whatsapp",
                "whatsapp_numero": "+55 (64) 99999-9999",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("aba=whatsapp", response.url)
        config = ConfiguracaoEntrega.get_solo()
        self.assertEqual(config.whatsapp_numero, "5564999999999")

    def test_whatsapp_tab_displays_saved_number(self):
        self.client.force_login(self.staff_user)
        config = ConfiguracaoEntrega.get_solo()
        config.whatsapp_numero = "5564999999999"
        config.save()

        response = self.client.get("/controle/ajustes/?aba=whatsapp")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WhatsApp oficial")
        self.assertContains(response, "5564999999999")

    def test_pix_key_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=pagamento",
            {
                "action": "save_pagamento",
                "pix_chave": "pix@pratodelivery.test",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("aba=pagamento", response.url)
        config = ConfiguracaoEntrega.get_solo()
        self.assertEqual(config.pix_chave, "pix@pratodelivery.test")

    def test_payment_tab_displays_saved_pix_key(self):
        self.client.force_login(self.staff_user)
        config = ConfiguracaoEntrega.get_solo()
        config.pix_chave = "pix@pratodelivery.test"
        config.save()

        response = self.client.get("/controle/ajustes/?aba=pagamento")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chave Pix")
        self.assertContains(response, "pix@pratodelivery.test")

    def test_users_tab_displays_user_and_class_management(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/controle/ajustes/?aba=usuarios")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adicionar")
        self.assertContains(response, "Gerenciar classes")
        self.assertContains(response, "Atendente")
        self.assertContains(response, "Somente super")

    def test_staff_cannot_create_user_from_users_tab(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/ajustes/?aba=usuarios",
            {
                "action": "create_user",
                "username": "novo_atendente",
                "password": "12345678",
                "is_active": "on",
                "is_staff": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Somente superusuarios podem administrar usuarios e classes.")
        self.assertFalse(get_user_model().objects.filter(username="novo_atendente").exists())

    def test_superuser_can_create_user_with_atendente_class(self):
        User = get_user_model()
        superuser = User.objects.create_superuser(username="admin_ajustes", password="12345678")
        group, _created = Group.objects.get_or_create(name="Atendente")
        self.client.force_login(superuser)

        response = self.client.post(
            "/controle/ajustes/?aba=usuarios",
            {
                "action": "create_user",
                "username": "novo_atendente",
                "first_name": "Novo Atendente",
                "email": "atendente@example.com",
                "password": "12345678",
                "groups": [str(group.id)],
                "is_active": "on",
                "is_staff": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username="novo_atendente")
        self.assertTrue(created.is_staff)
        self.assertTrue(created.groups.filter(name="Atendente").exists())

    def test_superuser_can_create_custom_class(self):
        superuser = get_user_model().objects.create_superuser(username="admin_classes", password="12345678")
        self.client.force_login(superuser)

        response = self.client.post(
            "/controle/ajustes/?aba=usuarios",
            {"action": "create_group", "group_name": "Gerente"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Group.objects.filter(name="Gerente").exists())


class FrontendConfigTests(TestCase):
    @override_settings(GOOGLE_MAPS_API_KEY="abcdef1234567890")
    def test_checkout_exposes_google_provider_configuration(self):
        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'googleMapsApiKey: "abcdef1234567890"')
        self.assertContains(response, 'checkoutMapProvider: "google"')

    def test_checkout_prefers_saved_google_configuration(self):
        config = ConfiguracaoEntrega.get_solo()
        config.google_maps_api_key = "salva-no-banco-456"
        config.google_maps_language = "pt-BR"
        config.google_maps_region = "BR"
        config.save()

        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'googleMapsApiKey: "salva\\u002Dno\\u002Dbanco\\u002D456"')
        self.assertContains(response, 'checkoutMapProvider: "google"')

    def test_checkout_displays_payment_stage(self):
        config = ConfiguracaoEntrega.get_solo()
        config.pix_chave = "pix@pratodelivery.test"
        config.save()

        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Itens escolhidos")
        self.assertContains(response, "Entrega")
        self.assertContains(response, "Pagamento")
        self.assertContains(response, "Online Pix")
        self.assertContains(response, "pix@pratodelivery.test")
        self.assertContains(response, "Copiar chave Pix")
        self.assertContains(response, 'data-copy-pix="pix@pratodelivery.test"')

    def test_checkout_hides_operator_address_search_for_public_customer(self):
        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-operator-checkout="false"')
        self.assertNotContains(response, "Busque o endereco do cliente")
        self.assertNotContains(response, "operator-address-query")

    def test_checkout_shows_operator_address_search_for_atendente_group(self):
        user = get_user_model().objects.create_user(username="atendente", password="senha")
        group, _created = Group.objects.get_or_create(name="Atendente")
        user.groups.add(group)
        self.client.force_login(user)

        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-operator-checkout="true"')
        self.assertContains(response, "Busque o endereco do cliente")
        self.assertContains(response, "operator-address-query")
        self.assertContains(response, "Ajustar no mapa")

    def test_checkout_superuser_without_atendente_group_uses_public_address_flow(self):
        user = get_user_model().objects.create_superuser(username="admin", password="senha")
        self.client.force_login(user)

        response = self.client.get("/checkout/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-operator-checkout="false"')
        self.assertNotContains(response, "Busque o endereco do cliente")

    def test_cardapio_displays_opening_hours_when_configured(self):
        config = ConfiguracaoEntrega.get_solo()
        config.horario_abertura = time(10, 30)
        config.horario_fechamento = time(14, 45)
        config.save()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARDÁPIO")
        self.assertContains(response, "Aberto 10:30 às 14:45")

    def test_cardapio_displays_whatsapp_float_when_number_is_configured(self):
        config = ConfiguracaoEntrega.get_solo()
        config.whatsapp_numero = "5564999999999"
        config.save()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "whatsapp-float")
        self.assertContains(response, "https://wa.me/5564999999999")
        self.assertContains(response, "Falar com atendente")

    def test_public_menu_uses_site_price_when_configured(self):
        Prato.objects.all().delete()
        Prato.objects.create(nome="Marmita Site", preco=Decimal("24.90"), preco_site=Decimal("27.50"), ativo=True)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "R$ 27,50")
        self.assertContains(response, '\\"preco\\": \\"27.50\\"')
        self.assertNotContains(response, "R$ 24,90")

    @override_settings(RESTAURANT_WHATSAPP="")
    def test_cardapio_hides_whatsapp_float_without_configured_number(self):
        ConfiguracaoEntrega.objects.update(whatsapp_numero="")

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "whatsapp-float")

    def test_carrinho_displays_cart_stage(self):
        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARRINHO")
        self.assertContains(response, "Itens escolhidos")
        self.assertContains(response, "Solicitar entrega")
        self.assertContains(response, "Fazer retirada")
        self.assertContains(response, "/pedido/retirada/")
        self.assertContains(response, "/checkout/")

    @patch("pedidos.views.timezone.localtime")
    def test_carrinho_displays_discreet_closed_notice_before_opening(self, mock_localtime):
        config = ConfiguracaoEntrega.get_solo()
        config.horario_abertura = time(10, 30)
        config.horario_fechamento = time(14, 45)
        config.save()
        mock_localtime.return_value = timezone.make_aware(datetime(2026, 5, 17, 9, 15))

        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cart-closed-note")
        self.assertContains(response, "Pedido antecipado")
        self.assertContains(response, "hoje")
        self.assertContains(response, "10:30")

    @patch("pedidos.views.timezone.localtime")
    def test_carrinho_closed_notice_after_closing_mentions_tomorrow(self, mock_localtime):
        config = ConfiguracaoEntrega.get_solo()
        config.horario_abertura = time(10, 30)
        config.horario_fechamento = time(14, 45)
        config.save()
        mock_localtime.return_value = timezone.make_aware(datetime(2026, 5, 17, 18, 0))

        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cart-closed-note")
        self.assertContains(response, "Pedido antecipado")
        self.assertContains(response, "amanh")
        self.assertContains(response, "10:30")

    @patch("pedidos.views.timezone.localtime")
    def test_carrinho_hides_closed_notice_while_open(self, mock_localtime):
        config = ConfiguracaoEntrega.get_solo()
        config.horario_abertura = time(10, 30)
        config.horario_fechamento = time(14, 45)
        config.save()
        mock_localtime.return_value = timezone.make_aware(datetime(2026, 5, 17, 11, 0))

        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "cart-closed-note")


class CardapioOperationalDayTests(TestCase):
    def setUp(self):
        Prato.objects.all().delete()
        config = ConfiguracaoEntrega.get_solo()
        config.horario_fechamento = time(14, 0)
        config.save()
        self.prato_segunda = Prato.objects.create(
            nome="Prato Segunda",
            preco=Decimal("25.00"),
            ativo=True,
            dias_disponiveis="seg",
        )
        self.prato_terca = Prato.objects.create(
            nome="Prato Terca",
            preco=Decimal("26.00"),
            ativo=True,
            dias_disponiveis="ter",
        )
        self.prato_quarta = Prato.objects.create(
            nome="Prato Quarta",
            preco=Decimal("27.00"),
            ativo=True,
            dias_disponiveis="qua",
        )

    def _local_datetime(self, year, month, day, hour, minute):
        return timezone.make_aware(datetime(year, month, day, hour, minute))

    @patch("pedidos.views.timezone.localtime")
    def test_before_closing_shows_current_day_as_prato_do_dia(self, mock_localtime):
        mock_localtime.return_value = self._local_datetime(2026, 5, 11, 13, 30)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<span>PRATO</span>", html=True)
        self.assertContains(response, "<span>DO DIA</span>", html=True)
        self.assertContains(response, "Prato Segunda")
        self.assertNotContains(response, "Prato Terca")

    @patch("pedidos.views.timezone.localtime")
    def test_after_closing_shows_next_day_prato_label(self, mock_localtime):
        mock_localtime.return_value = self._local_datetime(2026, 5, 11, 14, 30)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<span>PRATO</span>", html=True)
        self.assertContains(response, "<span>DE</span>", html=True)
        self.assertContains(response, "<span>TERÇA</span>", html=True)
        self.assertContains(response, "Prato Terca")
        self.assertNotContains(response, "Prato Segunda")

    @patch("pedidos.views.timezone.localtime")
    def test_after_closing_skips_to_next_available_prato_day(self, mock_localtime):
        self.prato_terca.ativo = False
        self.prato_terca.save()
        mock_localtime.return_value = self._local_datetime(2026, 5, 11, 14, 30)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<span>PRATO</span>", html=True)
        self.assertContains(response, "<span>DE</span>", html=True)
        self.assertContains(response, "<span>QUARTA</span>", html=True)
        self.assertContains(response, "Prato Quarta")
        self.assertNotContains(response, "Prato Terca")

    @patch("pedidos.context_processors.timezone.localtime")
    @patch("pedidos.views.timezone.localtime")
    def test_frontend_cart_cycle_moves_after_closing_time(self, mock_view_localtime, mock_context_localtime):
        current = self._local_datetime(2026, 5, 11, 14, 30)
        mock_view_localtime.return_value = current
        mock_context_localtime.return_value = current

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cartCycleKey: "2026\\u002D05\\u002D12"')
        self.assertContains(response, 'cartExpiresAt: "2026\\u002D05\\u002D12T14:00:00')

    @patch("pedidos.context_processors.timezone.localtime")
    @patch("pedidos.views.timezone.localtime")
    def test_frontend_cart_cycle_uses_current_day_before_closing_time(self, mock_view_localtime, mock_context_localtime):
        current = self._local_datetime(2026, 5, 11, 13, 30)
        mock_view_localtime.return_value = current
        mock_context_localtime.return_value = current

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cartCycleKey: "2026\\u002D05\\u002D11"')
        self.assertContains(response, 'cartExpiresAt: "2026\\u002D05\\u002D11T14:00:00')


class AdicionaisCatalogoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="adicionais_staff",
            password="12345678",
            is_staff=True,
        )

    def test_cardapio_displays_active_adicionais_as_separate_items(self):
        Adicional.objects.create(
            nome="Porcao extra de arroz",
            descricao="Serve uma pessoa",
            preco=Decimal("5.00"),
            ativo=True,
            ordem=10,
        )
        Adicional.objects.create(
            nome="Adicional inativo",
            preco=Decimal("4.00"),
            ativo=False,
            ordem=20,
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adicionais")
        self.assertContains(response, "Porcao extra de arroz")
        self.assertContains(response, '"tipo":"adicional"')
        self.assertNotContains(response, "Adicional inativo")

    def test_staff_can_create_and_toggle_adicional(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/controle/adicionais/salvar/",
            {
                "nome": "Farofa extra",
                "descricao": "Porcao individual",
                "preco": "4.50",
                "preco_ifood": "6.50",
                "ordem": "15",
                "ativo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        adicional = Adicional.objects.get(nome="Farofa extra")
        self.assertTrue(adicional.ativo)
        self.assertEqual(adicional.preco, Decimal("4.50"))
        self.assertEqual(adicional.preco_ifood, Decimal("6.50"))

        response = self.client.post(f"/controle/adicionais/{adicional.id}/alternar/")

        self.assertEqual(response.status_code, 302)
        adicional.refresh_from_db()
        self.assertFalse(adicional.ativo)

    def test_staff_can_delete_catalog_image_without_page_reload(self):
        self.client.force_login(self.staff_user)
        adicional = Adicional.objects.create(
            nome="Farofa extra",
            preco=Decimal("4.50"),
            ativo=True,
            imagem=SimpleUploadedFile("farofa.png", b"imagem-teste", content_type="image/png"),
        )

        response = self.client.post(
            f"/controle/adicionais/{adicional.id}/imagem/excluir/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        adicional.refresh_from_db()
        self.assertFalse(adicional.imagem)


class AddressApiTests(TestCase):
    def test_autocomplete_endpoint_was_removed_from_public_api(self):
        response = self.client.get("/api/address/autocomplete/?q=Rua%20Teste%2010")

        self.assertEqual(response.status_code, 404)

    def test_reverse_geocode_endpoint_was_removed_from_public_api(self):
        response = self.client.get("/api/address/reverse-geocode/?lat=-17.79&lng=-50.91")

        self.assertEqual(response.status_code, 404)

    def test_delivery_time_requires_saved_origin(self):
        response = self.client.get("/api/address/delivery-time/?lat=-17.77&lng=-50.90")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "origin_not_configured")

class CriarPedidoFreteTests(TestCase):
    def setUp(self):
        self.prato = Prato.objects.create(
            nome="Frango Guisado",
            preco=Decimal("24.90"),
            ativo=True,
        )
        self.bebida = Bebida.objects.create(
            nome="Coca-Cola 350ml",
            preco=Decimal("6.00"),
            ativo=True,
            ordem=10,
        )
        self.adicional = Adicional.objects.create(
            nome="Porcao extra de arroz",
            preco=Decimal("5.00"),
            ativo=True,
            ordem=20,
        )
        config = ConfiguracaoEntrega.get_solo()
        config.origem_endereco = "Ponto confirmado no mapa"
        config.origem_latitude = Decimal("-17.7923000")
        config.origem_longitude = Decimal("-50.9192000")
        config.whatsapp_numero = "5564999999999"
        config.pix_chave = "pix@pratodelivery.test"
        config.save()
        FaixaFrete.objects.bulk_create(
            [
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("5.00"), valor=Decimal("10.00"), ordem=10, ativo=True),
                FaixaFrete(tipo=FaixaFrete.Tipo.ATE, km_limite=Decimal("10.00"), valor=Decimal("20.00"), ordem=20, ativo=True),
            ]
        )

    def _delivery_payload(self, checkout_key="checkout-key-1234567890"):
        return {
            "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
            "nome_cliente": "Cliente Teste",
            "telefone": "64999999999",
            "rua": "Rua Teste",
            "numero": "10",
            "bairro": "Centro",
            "cidade": "Rio Verde",
            "estado": "GO",
            "latitude": "-17.7707268",
            "longitude": "-50.9003217",
            "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
            "geocode_tipo": "house",
            "geocode_precision": "exact",
            "valor_frete": "5.00",
            "distancia_km": "1.00",
            "forma_pagamento": Pedido.FormaPagamento.PIX,
            "checkout_key": checkout_key,
        }

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    def test_ajax_order_creation_returns_public_payload_and_cookie(self, _mock_route):
        response = self.client.post(
            "/pedido/criar/",
            self._delivery_payload(),
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        pedido = Pedido.objects.get()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["reused"])
        self.assertEqual(payload["pedido"]["token"], pedido.public_token)
        self.assertEqual(payload["success_url"], f"/pedido/{pedido.public_token}/sucesso/")
        self.assertEqual(pedido.checkout_key, "entrega:checkout-key-1234567890")
        self.assertIn(ORDER_HISTORY_COOKIE, response.cookies)

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    def test_checkout_key_retry_returns_existing_order_without_duplicate(self, mock_route):
        first_response = self.client.post(
            "/pedido/criar/",
            self._delivery_payload(),
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second_response = self.client.post(
            "/pedido/criar/",
            self._delivery_payload(),
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertTrue(second_response.json()["reused"])
        self.assertEqual(second_response.json()["pedido"]["token"], first_response.json()["pedido"]["token"])
        self.assertEqual(mock_route.call_count, 1)

    def test_pickup_checkout_key_retry_returns_existing_order_without_duplicate(self):
        payload = {
            "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
            "nome_cliente": "Cliente Retirada",
            "observacao_geral": "Retiro no balcao",
            "enviar_talheres": "nao",
            "checkout_key": "pickup-key-1234567890",
        }

        first_response = self.client.post(
            "/pedido/retirada/",
            payload,
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second_response = self.client.post(
            "/pedido/retirada/",
            payload,
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertTrue(second_response.json()["reused"])
        self.assertEqual(Pedido.objects.get().checkout_key, "retirada:pickup-key-1234567890")

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 5870.0))
    def test_server_recalculates_distance_and_shipping_from_resolved_destination(self, _mock_route):
        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "lote_quadra": "Qd. 12 Lt. 04",
                "complemento": "Casa 2",
                "ponto_referencia": "Portao branco",
                "valor_frete": "5.00",
                "distancia_km": "1.00",
                "forma_pagamento": Pedido.FormaPagamento.PIX,
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.PIX)
        self.assertEqual(pedido.distancia_km, Decimal("5.87"))
        self.assertEqual(pedido.valor_frete, Decimal("20.00"))
        self.assertEqual(pedido.total, Decimal("44.90"))
        self.assertEqual(pedido.lote_quadra, "Qd. 12 Lt. 04")
        self.assertEqual(pedido.complemento, "Casa 2")
        self.assertEqual(pedido.ponto_referencia, "Portao branco")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/pedido/{pedido.public_token}/sucesso/")

        success_response = self.client.get(response.url)
        self.assertContains(success_response, "Pedido finalizado")
        self.assertContains(success_response, "Abrir WhatsApp agora")
        self.assertContains(success_response, "Redirecionando voce ao WhatsApp")
        self.assertContains(success_response, "data-whatsapp-countdown")
        self.assertContains(success_response, "https://wa.me/5564999999999?text=")
        self.assertNotContains(success_response, "window.open")
        self.assertContains(success_response, "/meus-pedidos/")

        lookup_response = self.client.post(
            "/api/meus-pedidos/",
            data='{"tokens":["%s"]}' % pedido.public_token,
            content_type="application/json",
        )
        self.assertEqual(lookup_response.status_code, 200)
        self.assertEqual(lookup_response.json()["pedidos"][0]["numero"], pedido.numero)
        self.assertEqual(
            lookup_response.json()["pedidos"][0]["acompanhamento_url"],
            f"/pedido/{pedido.public_token}/acompanhar/",
        )

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    def test_order_creation_accepts_bebida_as_independent_item(self, _mock_route):
        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"tipo": "bebida", "item_id": %d, "quantidade": 2, "preco": "6.00"}]' % self.bebida.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "0.00",
                "distancia_km": "0.00",
                "forma_pagamento": Pedido.FormaPagamento.DINHEIRO,
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        item = pedido.itens.get()
        self.assertIsNone(item.prato)
        self.assertEqual(item.bebida, self.bebida)
        self.assertEqual(item.nome_prato_snapshot, "Coca-Cola 350ml")
        self.assertEqual(item.subtotal, Decimal("12.00"))
        self.assertEqual(pedido.total, Decimal("22.00"))
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.DINHEIRO)

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    def test_order_creation_accepts_adicional_as_independent_item(self, _mock_route):
        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"tipo": "adicional", "item_id": %d, "quantidade": 3, "preco": "5.00"}]' % self.adicional.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "0.00",
                "distancia_km": "0.00",
                "forma_pagamento": Pedido.FormaPagamento.CARTAO,
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        item = pedido.itens.get()
        self.assertIsNone(item.prato)
        self.assertIsNone(item.bebida)
        self.assertEqual(item.adicional, self.adicional)
        self.assertEqual(item.nome_prato_snapshot, "Porcao extra de arroz")
        self.assertEqual(item.subtotal, Decimal("15.00"))
        self.assertEqual(pedido.total, Decimal("25.00"))
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.CARTAO)

    @patch("pedidos.views._fetch_route_summary")
    def test_online_pix_requires_configured_key(self, mock_route):
        ConfiguracaoEntrega.objects.update(pix_chave="")

        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "5.00",
                "distancia_km": "1.00",
                "forma_pagamento": Pedido.FormaPagamento.PIX,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Configure a chave Pix", status_code=400)
        mock_route.assert_not_called()
        self.assertFalse(Pedido.objects.exists())

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    def test_order_creation_allows_blank_customer_name(self, _mock_route):
        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "0.00",
                "distancia_km": "0.00",
                "forma_pagamento": Pedido.FormaPagamento.DINHEIRO,
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.nome_cliente, "Cliente")

    def test_pickup_order_creation_saves_approval_order_without_shipping(self):
        response = self.client.post(
            "/pedido/retirada/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Retirada",
                "observacao_geral": "Retiro no balcao",
                "enviar_talheres": "nao",
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(pedido.nome_cliente, "Cliente Retirada")
        self.assertEqual(pedido.endereco, "Retirada no local")
        self.assertEqual(pedido.tipo_coleta, Pedido.TipoColeta.RETIRADA)
        self.assertEqual(pedido.icone_pedido, Pedido.icon_path_for_number(pedido.numero))
        self.assertEqual(pedido.valor_frete, Decimal("0.00"))
        self.assertEqual(pedido.distancia_km, Decimal("0.00"))
        self.assertEqual(pedido.total, Decimal("24.90"))
        self.assertFalse(pedido.enviar_talheres)
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.DINHEIRO)

    def test_pickup_order_applies_fifth_meal_promotion(self):
        response = self.client.post(
            "/pedido/retirada/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 5, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Retirada",
                "observacao_geral": "",
                "enviar_talheres": "sim",
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.total_sem_desconto, Decimal("124.50"))
        self.assertEqual(pedido.promocao_descricao, "5ª marmita grátis")
        self.assertEqual(pedido.promocao_desconto, Decimal("24.90"))
        self.assertEqual(pedido.total, Decimal("99.60"))
        success_response = self.client.get(response.url)
        self.assertContains(success_response, "5ª marmita grátis")
        self.assertContains(success_response, "- R$ 24,90")

    @override_settings(RESTAURANT_WHATSAPP="556488887777")
    def test_pickup_order_creation_uses_whatsapp_env_fallback(self):
        ConfiguracaoEntrega.objects.update(whatsapp_numero="")

        response = self.client.post(
            "/pedido/retirada/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Retirada",
                "observacao_geral": "Retiro no balcao",
                "enviar_talheres": "sim",
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(response.url, f"/pedido/{pedido.public_token}/sucesso/")
        success_response = self.client.get(response.url)
        self.assertContains(success_response, "Abrir WhatsApp agora")
        self.assertContains(success_response, "Redirecionando voce ao WhatsApp")
        self.assertContains(success_response, "data-whatsapp-countdown")
        self.assertContains(success_response, f"https://wa.me/556488887777?text=")
        self.assertNotContains(success_response, "window.open")
        self.assertContains(success_response, "/meus-pedidos/")
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)

    @patch("pedidos.views._fetch_route_summary")
    @override_settings(RESTAURANT_WHATSAPP="")
    def test_order_creation_requires_configured_whatsapp(self, mock_route):
        ConfiguracaoEntrega.objects.update(whatsapp_numero="")

        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "5.00",
                "distancia_km": "1.00",
                "forma_pagamento": Pedido.FormaPagamento.PIX,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Configure o número do WhatsApp", status_code=400)
        mock_route.assert_not_called()
        self.assertFalse(Pedido.objects.exists())

    @patch("pedidos.views._fetch_route_summary", return_value=(780.0, 1200.0))
    @override_settings(RESTAURANT_WHATSAPP="556488887777")
    def test_order_creation_uses_whatsapp_env_fallback(self, _mock_route):
        ConfiguracaoEntrega.objects.update(whatsapp_numero="")

        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "5.00",
                "distancia_km": "1.00",
                "forma_pagamento": Pedido.FormaPagamento.DINHEIRO,
            },
        )

        self.assertEqual(response.status_code, 302)
        pedido = Pedido.objects.get()
        success_response = self.client.get(response.url)
        self.assertContains(success_response, f"https://wa.me/556488887777?text=")
        self.assertEqual(pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)

    @patch("pedidos.views._fetch_route_summary")
    def test_order_creation_requires_saved_origin(self, mock_route):
        ConfiguracaoEntrega.objects.update(origem_endereco="", origem_latitude=None, origem_longitude=None)

        response = self.client.post(
            "/pedido/criar/",
            {
                "carrinho_payload": '[{"prato_id": %d, "quantidade": 1, "preco": "24.90"}]' % self.prato.id,
                "nome_cliente": "Cliente Teste",
                "telefone": "64999999999",
                "rua": "Rua Teste",
                "numero": "10",
                "bairro": "Centro",
                "cidade": "Rio Verde",
                "estado": "GO",
                "latitude": "-17.7707268",
                "longitude": "-50.9003217",
                "endereco_formatado": "Rua Teste, 10, Centro, Rio Verde - GO",
                "geocode_tipo": "house",
                "geocode_precision": "exact",
                "valor_frete": "5.00",
                "distancia_km": "1.00",
                "forma_pagamento": Pedido.FormaPagamento.PIX,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Configure e salve a origem", status_code=400)
        mock_route.assert_not_called()
        self.assertFalse(Pedido.objects.exists())


