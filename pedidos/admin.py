from django.contrib import admin
from django.utils.html import format_html

from .models import Adicional, Bebida, ConfiguracaoEntrega, Cupom, FaixaFrete, ItemPedido, Pedido, Prato

admin.site.site_header = "PRATO-DELIVERY Admin"
admin.site.site_title = "PRATO-DELIVERY"
admin.site.index_title = "Gestão do delivery"


@admin.register(Prato)
class PratoAdmin(admin.ModelAdmin):
    list_display = ("nome", "preco", "ativo", "dias_disponiveis", "criado_em")
    list_editable = ("preco", "ativo", "dias_disponiveis")
    list_filter = ("ativo", "criado_em")
    search_fields = ("nome", "descricao", "variacoes", "dias_disponiveis")
    list_per_page = 25
    fieldsets = (
        ("Dados do prato", {"fields": ("nome", "descricao", "variacoes", "imagem")}),
        ("Publicacao", {"fields": ("preco", "ativo", "dias_disponiveis")}),
    )


@admin.register(Bebida)
class BebidaAdmin(admin.ModelAdmin):
    list_display = ("nome", "preco", "ativo", "ordem", "criado_em")
    list_editable = ("preco", "ativo", "ordem")
    list_filter = ("ativo", "criado_em")
    search_fields = ("nome", "descricao")
    ordering = ("ordem", "nome")
    list_per_page = 25


@admin.register(Adicional)
class AdicionalAdmin(admin.ModelAdmin):
    list_display = ("nome", "preco", "ativo", "ordem", "criado_em")
    list_editable = ("preco", "ativo", "ordem")
    list_filter = ("ativo", "criado_em")
    search_fields = ("nome", "descricao")
    ordering = ("ordem", "nome")
    list_per_page = 25


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = (
        "prato",
        "bebida",
        "adicional",
        "nome_prato_snapshot",
        "preco_snapshot",
        "quantidade",
        "observacao",
        "subtotal",
    )
    can_delete = False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "nome_cliente",
        "telefone",
        "bairro",
        "cidade",
        "rota_google_maps",
        "forma_pagamento",
        "enviar_talheres",
        "status",
        "valor_frete",
        "total",
        "criado_em",
    )
    list_editable = ("status",)
    list_filter = ("status", "forma_pagamento", "enviar_talheres", "criado_em")
    search_fields = ("numero", "nome_cliente", "telefone", "rua", "numero_endereco", "bairro", "cidade", "endereco")
    readonly_fields = ("numero", "total", "criado_em", "rota_google_maps")
    list_per_page = 25
    inlines = [ItemPedidoInline]
    fieldsets = (
        ("Cliente", {"fields": ("nome_cliente", "telefone")}),
        (
            "Endereço",
            {
                "fields": (
                    "rua",
                    "numero_endereco",
                    "bairro",
                    "lote_quadra",
                    "ponto_referencia",
                    "cidade",
                    "estado",
                    "endereco_formatado",
                    "latitude",
                    "longitude",
                    "endereco",
                    "complemento",
                )
            },
        ),
        ("Rota", {"fields": ("rota_google_maps",)}),
        (
            "Pedido",
            {
                "fields": (
                    "forma_pagamento",
                    "enviar_talheres",
                    "observacao_geral",
                    "status",
                    "distancia_km",
                    "valor_frete",
                    "total",
                    "numero",
                    "criado_em",
                )
            },
        ),
    )

    @admin.display(description="Rota")
    def rota_google_maps(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Abrir rota no Google Maps</a>',
            obj.google_maps_route_url,
        )


@admin.register(ItemPedido)
class ItemPedidoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "nome_prato_snapshot", "variacao_nome_snapshot", "quantidade", "subtotal")
    list_select_related = ("pedido", "prato", "bebida", "adicional")
    search_fields = ("nome_prato_snapshot", "variacao_nome_snapshot", "pedido__nome_cliente", "pedido__numero")


@admin.register(FaixaFrete)
class FaixaFreteAdmin(admin.ModelAdmin):
    list_display = ("tipo", "km_limite", "valor", "ativo", "ordem")
    list_editable = ("km_limite", "valor", "ativo", "ordem")
    list_filter = ("tipo", "ativo")
    ordering = ("ordem", "km_limite", "id")


@admin.register(Cupom)
class CupomAdmin(admin.ModelAdmin):
    list_display = ("codigo", "tipo_desconto", "valor", "valor_minimo_pedido", "ativo", "uso_maximo_total")
    list_filter = ("ativo", "tipo_desconto")
    search_fields = ("codigo", "descricao")


@admin.register(ConfiguracaoEntrega)
class ConfiguracaoEntregaAdmin(admin.ModelAdmin):
    list_display = ("origem_endereco", "origem_latitude", "origem_longitude", "google_maps_habilitado", "atualizado_em")
    readonly_fields = ("criado_em", "atualizado_em")
    fields = (
        "horario_abertura",
        "horario_fechamento",
        "origem_endereco",
        "origem_latitude",
        "origem_longitude",
        "google_maps_api_key",
        "google_maps_language",
        "google_maps_region",
        "criado_em",
        "atualizado_em",
    )

    @admin.display(description="Google Maps")
    def google_maps_habilitado(self, obj):
        return "Configurado" if obj.google_maps_api_key_effective else "Fallback"
