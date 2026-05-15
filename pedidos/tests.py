import json

from decimal import Decimal
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import Adicional, Bebida, Cliente, ClienteTokenConflito, ConfiguracaoEntrega, Cupom, EnderecoCliente, FaixaFrete, ItemPedido, Pedido, Prato
from .order_services import create_order_items_from_payload, inherit_customer_from_known_tokens, sync_customer_from_order
from .utils import build_google_maps_route_url
from .views import ORDER_HISTORY_COOKIE, _calcular_frete_por_distancia


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

    def test_requires_staff_authentication(self):
        response = self.client.get("/api/pedidos/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_rejects_authenticated_user_without_staff_permission(self):
        self.client.force_login(self.regular_user)

        response = self.client.get("/api/pedidos/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_authenticated_list_returns_orders(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/api/pedidos/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["pedidos"][0]["id"], self.pedido.id)

    def test_authenticated_detail_returns_main_fields_and_coupon(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(f"/api/pedidos/{self.pedido.id}/")

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
        self.assertEqual(pedido["valor_frete"], "10.00")
        self.assertEqual(pedido["total"], "30.00")
        self.assertEqual(pedido["cupom"]["id"], self.cupom.id)
        self.assertEqual(pedido["cupom"]["codigo"], "API10")

    def test_includes_order_items(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(f"/api/pedidos/{self.pedido.id}/")

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
        self.client.force_login(self.staff_user)

        response = self.client.get("/api/pedidos/?status=em_preparo&tipo_coleta=entrega&telefone=9999")

        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["pedidos"][0]["id"], self.pedido.id)


class PublicFlowCacheTests(TestCase):
    def test_cart_checkout_and_menu_are_not_browser_cached(self):
        for path in ["/", "/carrinho/", "/checkout/"]:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))


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
        Prato.objects.create(nome="Carreteiro", preco=Decimal("25.00"), ativo=True)

        response = self.client.get("/controle/api/catalogo-editor/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["nome"], "Carreteiro")

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
        self.assertContains(response, "?status=em_preparo")

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

    def test_carrinho_displays_cart_stage(self):
        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARRINHO")
        self.assertContains(response, "Itens escolhidos")
        self.assertContains(response, "Solicitar entrega")
        self.assertContains(response, "Fazer retirada")
        self.assertContains(response, "/pedido/retirada/")
        self.assertContains(response, "/checkout/")


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
        self.assertContains(response, "<span>TERCA</span>", html=True)
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
                "ordem": "15",
                "ativo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        adicional = Adicional.objects.get(nome="Farofa extra")
        self.assertTrue(adicional.ativo)
        self.assertEqual(adicional.preco, Decimal("4.50"))

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
        self.assertContains(success_response, "Pedido recebido")
        self.assertContains(success_response, "Abrir WhatsApp")
        self.assertContains(success_response, "Abrindo WhatsApp")
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
        self.assertContains(success_response, "Abrir WhatsApp")
        self.assertContains(success_response, "Abrindo WhatsApp")
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


