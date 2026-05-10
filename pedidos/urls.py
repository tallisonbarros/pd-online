from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("", views.cardapio, name="cardapio"),
    path("dashboard/api/order-heatmap/", views.api_order_heatmap, name="api_order_heatmap"),
    path("dashboard/api/bairros-rio-verde/", views.api_bairros_rio_verde, name="api_bairros_rio_verde"),
    path("dashboard/api/bairros-polygons/", views.api_bairros_polygons, name="api_bairros_polygons"),
    path("api/address/autocomplete/", views.api_address_autocomplete, name="api_address_autocomplete"),
    path("api/address/reverse-geocode/", views.api_address_reverse_geocode, name="api_address_reverse_geocode"),
    path("api/address/delivery-time/", views.api_address_delivery_time, name="api_address_delivery_time"),
    path("carrinho/", views.carrinho, name="carrinho"),
    path("checkout/", views.checkout, name="checkout"),
    path("pedido/criar/", views.criar_pedido, name="criar_pedido"),
    path("pedido/retirada/", views.criar_retirada, name="criar_retirada"),
    path("pedido/<int:numero>/sucesso/", views.sucesso, name="sucesso"),
    path("cozinha/", views.cozinha, name="cozinha"),
    path("cozinha/cozinha/", views.cozinha_pedidos, name="cozinha_operacao"),
    path("cozinha/pedidos/", views.pedidos_admin, name="cozinha_pedidos"),
    path("cozinha/pedidos/<int:pedido_id>/", views.pedido_detalhe_admin, name="pedido_detalhe_admin"),
    path("cozinha/ajustes/", views.ajustes_admin, name="ajustes_admin"),
    path("cozinha/pratos/", views.gestao_pratos, name="gestao_pratos"),
    path("cozinha/bebidas/", views.gestao_bebidas, name="gestao_bebidas"),
    path("cozinha/adicionais/", views.adicionais_admin, name="adicionais_admin"),
    path("cozinha/outros/", views.outros_admin, name="outros_admin"),
    path("cozinha/cupons/", views.cupons_admin, name="cupons_admin"),
    path("cozinha/pratos/salvar/", views.salvar_prato, name="salvar_prato"),
    path("cozinha/pratos/<int:prato_id>/alternar/", views.alternar_prato, name="alternar_prato"),
    path("cozinha/bebidas/salvar/", views.salvar_bebida, name="salvar_bebida"),
    path("cozinha/bebidas/<int:bebida_id>/alternar/", views.alternar_bebida, name="alternar_bebida"),
    path("cozinha/api/pedidos/", views.api_pedidos_cozinha, name="api_pedidos_cozinha"),
    path("cozinha/api/operacao/", views.api_cozinha_operacao, name="api_cozinha_operacao"),
    path("cozinha/pedido/<int:pedido_id>/status/", views.atualizar_status_pedido, name="atualizar_status_pedido"),
]
