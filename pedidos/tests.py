from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import Bebida, ConfiguracaoEntrega, FaixaFrete, ItemPedido, Pedido, Prato
from .utils import build_google_maps_route_url
from .views import _calcular_frete_por_distancia


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
        response = self.client.get("/cozinha/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_live_orders_api_requires_staff_authentication(self):
        response = self.client.get("/cozinha/api/pedidos/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_access_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/cozinha/")

        self.assertEqual(response.status_code, 200)


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
        response = self.client.get(f"/cozinha/pedidos/{pedido.id}/")
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

        response = self.client.get(f"/cozinha/pedidos/{pedido.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frete salvo")
        self.assertContains(response, "Distancia calculada")
        self.assertEqual(response.context["pedido"], pedido)
        self.assertEqual(response.context["frete_esperado"], Decimal("10.00"))
        self.assertEqual(response.context["itens_subtotal"], Decimal("24.00"))
        self.assertTrue(response.context["frete_confere"])

    def test_orders_admin_shows_approval_queue(self):
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

        response = self.client.get("/cozinha/pedidos/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pedidos para aprovacao")
        self.assertContains(response, "Aprovar pedido")
        self.assertIn(pedido, list(response.context["pedidos_aprovacao"]))


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
        response = self.client.get("/cozinha/ajustes/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_saves_origin_and_faixa_updates(self):
        self.client.force_login(self.staff_user)
        faixa = FaixaFrete.objects.order_by("ordem").first()

        response = self.client.post(
            "/cozinha/ajustes/",
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
            "/cozinha/ajustes/",
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
    @patch(
        "pedidos.views._resolve_address_result",
        return_value={
            "label": "Rua Teste, Centro, Rio Verde - GO",
            "lat": -17.77,
            "lng": -50.90,
            "type": "street",
        },
    )
    def test_preview_uses_current_form_values(self, _mock_resolve, _mock_route):
        self.client.force_login(self.staff_user)
        faixas = list(FaixaFrete.objects.order_by("ordem"))

        response = self.client.post(
            "/cozinha/ajustes/",
            {
                "action": "test_frete",
                "origem_endereco": "Rua B, 22 - Centro, Rio Verde - GO",
                "origem_latitude": "-17.8010000",
                "origem_longitude": "-50.9110000",
                "destino_teste": "Rua Teste, 50 - Centro, Rio Verde - GO",
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
        self.assertContains(response, "Este teste usou uma origem ainda nao salva")

    @override_settings(GOOGLE_MAPS_API_KEY="abcdef1234567890", GOOGLE_MAPS_LANGUAGE="pt-BR", GOOGLE_MAPS_REGION="BR")
    def test_google_tab_displays_provider_status(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/cozinha/ajustes/?aba=google")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google Maps")
        self.assertContains(response, "abcdef...7890")
        self.assertContains(response, "Maps JavaScript API")
        self.assertContains(response, "Geocoding API")

    def test_google_settings_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/cozinha/ajustes/?aba=google",
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
            "/cozinha/ajustes/?aba=whatsapp",
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

        response = self.client.get("/cozinha/ajustes/?aba=whatsapp")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WhatsApp oficial")
        self.assertContains(response, "5564999999999")

    def test_pix_key_can_be_saved_from_ajustes(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            "/cozinha/ajustes/?aba=pagamento",
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

        response = self.client.get("/cozinha/ajustes/?aba=pagamento")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chave Pix")
        self.assertContains(response, "pix@pratodelivery.test")


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

    def test_carrinho_displays_cart_stage(self):
        response = self.client.get("/carrinho/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARRINHO")
        self.assertContains(response, "Itens escolhidos")
        self.assertContains(response, "Solicitar entrega")
        self.assertContains(response, "Fazer retirada")
        self.assertContains(response, "/pedido/retirada/")
        self.assertContains(response, "/checkout/")


class AddressApiTests(TestCase):
    @patch(
        "pedidos.views._fetch_photon_features",
        return_value=[
            {
                "properties": {
                    "street": "Rua Teste",
                    "housenumber": "10",
                    "district": "Centro",
                    "city": "Rio Verde",
                    "state": "GO",
                    "country": "Brasil",
                    "countrycode": "br",
                    "type": "house",
                },
                "geometry": {"coordinates": [-50.91, -17.79]},
            }
        ],
    )
    def test_autocomplete_returns_precision_metadata(self, _mock_fetch):
        response = self.client.get("/api/address/autocomplete/?q=Rua%20Teste%2010")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["precision"], "exact")
        self.assertEqual(payload[0]["precision_label"], "Endereco confirmado")
        self.assertEqual(payload[0]["type"], "house")

    @patch(
        "pedidos.views._fetch_photon_features",
        return_value=[
            {
                "properties": {
                    "street": "Rua Jose Duarte de Sousa",
                    "district": "Residencial Monte Siao",
                    "city": "Rio Verde",
                    "state": "GO",
                    "country": "Brasil",
                    "countrycode": "br",
                    "type": "street",
                },
                "geometry": {"coordinates": [-50.90, -17.77]},
            },
            {
                "properties": {
                    "street": "Rua Jose Duarte de Sousa",
                    "district": "Maranata",
                    "city": "Rio Verde",
                    "state": "GO",
                    "country": "Brasil",
                    "countrycode": "br",
                    "type": "street",
                },
                "geometry": {"coordinates": [-50.901, -17.771]},
            },
        ],
    )
    def test_autocomplete_prioritizes_matching_bairro_hint(self, _mock_fetch):
        response = self.client.get("/api/address/autocomplete/?q=jose+duarte&bairro=Maranata&cidade=Rio+Verde&estado=GO")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["district"], "Maranata")

    @patch(
        "pedidos.views._reverse_geocode_result",
        return_value={
            "label": "Rua Teste, Centro, Rio Verde - GO",
            "street": "Rua Teste",
            "number": "",
            "district": "Centro",
            "city": "Rio Verde",
            "state": "GO",
            "country": "Brasil",
            "lat": -17.79,
            "lng": -50.91,
            "type": "street",
            "precision": "approximate",
            "precision_label": "Endereco aproximado",
        },
    )
    def test_reverse_geocode_returns_expected_payload(self, _mock_reverse):
        response = self.client.get("/api/address/reverse-geocode/?lat=-17.79&lng=-50.91")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["street"], "Rua Teste")
        self.assertEqual(payload["district"], "Centro")
        self.assertEqual(payload["source"], "reverse")

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
        self.assertEqual(response.url, f"/pedido/{pedido.numero}/sucesso/")

        success_response = self.client.get(response.url)
        self.assertContains(success_response, "Pedido encerrado")
        self.assertContains(success_response, "Finalizar no WhatsApp")
        self.assertContains(success_response, "Redirecionando para o WhatsApp em")
        self.assertContains(success_response, "data-whatsapp-countdown")
        self.assertContains(success_response, "https://wa.me/5564999999999?text=")
        self.assertNotContains(success_response, "window.open")

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
        self.assertEqual(pedido.valor_frete, Decimal("0.00"))
        self.assertEqual(pedido.distancia_km, Decimal("0.00"))
        self.assertEqual(pedido.total, Decimal("24.90"))
        self.assertFalse(pedido.enviar_talheres)
        self.assertEqual(pedido.forma_pagamento, Pedido.FormaPagamento.DINHEIRO)

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
        success_response = self.client.get(response.url)
        self.assertContains(success_response, "Finalizar no WhatsApp")
        self.assertContains(success_response, "Redirecionando para o WhatsApp em")
        self.assertContains(success_response, "data-whatsapp-countdown")
        self.assertContains(success_response, f"https://wa.me/556488887777?text=")
        self.assertNotContains(success_response, "window.open")
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
        self.assertContains(response, "Configure o numero do WhatsApp", status_code=400)
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
