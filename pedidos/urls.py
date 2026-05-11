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
    path("controle/", views.cozinha, name="cozinha"),
    path("controle/operacao/", views.cozinha_pedidos, name="cozinha_operacao"),
    path("controle/pedidos/", views.pedidos_admin, name="cozinha_pedidos"),
    path("controle/pedidos/<int:pedido_id>/", views.pedido_detalhe_admin, name="pedido_detalhe_admin"),
    path("controle/ajustes/", views.ajustes_admin, name="ajustes_admin"),
    path("controle/pratos/", views.gestao_pratos, name="gestao_pratos"),
    path("controle/bebidas/", views.gestao_bebidas, name="gestao_bebidas"),
    path("controle/adicionais/", views.adicionais_admin, name="adicionais_admin"),
    path("controle/outros/", views.outros_admin, name="outros_admin"),
    path("controle/cupons/", views.cupons_admin, name="cupons_admin"),
    path("controle/pratos/salvar/", views.salvar_prato, name="salvar_prato"),
    path("controle/pratos/<int:prato_id>/alternar/", views.alternar_prato, name="alternar_prato"),
    path("controle/pratos/<int:prato_id>/imagem/excluir/", views.excluir_imagem_prato, name="excluir_imagem_prato"),
    path("controle/bebidas/salvar/", views.salvar_bebida, name="salvar_bebida"),
    path("controle/bebidas/<int:bebida_id>/alternar/", views.alternar_bebida, name="alternar_bebida"),
    path("controle/bebidas/<int:bebida_id>/imagem/excluir/", views.excluir_imagem_bebida, name="excluir_imagem_bebida"),
    path("controle/adicionais/salvar/", views.salvar_adicional, name="salvar_adicional"),
    path("controle/adicionais/<int:adicional_id>/alternar/", views.alternar_adicional, name="alternar_adicional"),
    path("controle/adicionais/<int:adicional_id>/imagem/excluir/", views.excluir_imagem_adicional, name="excluir_imagem_adicional"),
    path("controle/api/pedidos/", views.api_pedidos_cozinha, name="api_pedidos_cozinha"),
    path("controle/api/operacao/", views.api_cozinha_operacao, name="api_cozinha_operacao"),
    path("controle/pedido/<int:pedido_id>/status/", views.atualizar_status_pedido, name="atualizar_status_pedido"),
]
