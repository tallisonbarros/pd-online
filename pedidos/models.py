from decimal import Decimal
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

PEDIDO_ICON_FOLDER = "img/Icones_pedidos"
PEDIDO_ICON_COUNT = 30


class Prato(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    variacoes = models.TextField(
        blank=True,
        help_text="Uma variacao por linha. Ex.: Fraldinha, Frango.",
    )
    imagem = models.ImageField(upload_to="pratos/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_balcao = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_site = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_ifood = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    dias_disponiveis = models.CharField(
        max_length=120,
        blank=True,
        help_text="Ex.: seg,ter,qua ou deixe vazio para todos os dias.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def preco_site_resolvido(self):
        return self.preco_site if self.preco_site is not None else self.preco


class Bebida(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    imagem = models.ImageField(upload_to="bebidas/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_balcao = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_site = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_ifood = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome

    @property
    def preco_site_resolvido(self):
        return self.preco_site if self.preco_site is not None else self.preco


class Adicional(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    imagem = models.ImageField(upload_to="adicionais/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_balcao = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_site = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    preco_ifood = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome

    @property
    def preco_site_resolvido(self):
        return self.preco_site if self.preco_site is not None else self.preco


class Cliente(models.Model):
    telefone_normalizado = models.CharField(max_length=20, unique=True)
    telefone = models.CharField(max_length=30)
    nome = models.CharField(max_length=120)
    nome_editado_manualmente = models.BooleanField(default=False)
    primeiro_pedido_em = models.DateTimeField(blank=True, null=True)
    ultimo_pedido_em = models.DateTimeField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ultimo_pedido_em", "nome"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.nome} - {self.telefone}"


class ResumoOperacionalDia(models.Model):
    data = models.DateField(unique=True)
    marmitas_produzidas = models.PositiveIntegerField(default=0)
    consumo_interno = models.PositiveIntegerField(default=0)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data"]
        verbose_name = "Resumo operacional do dia"
        verbose_name_plural = "Resumos operacionais do dia"

    def __str__(self):
        return f"Resumo operacional - {self.data:%d/%m/%Y}"


class Pedido(models.Model):
    class Canal(models.TextChoices):
        BALCAO = "balcao", "Balcao"
        SITE = "site", "Site"
        IFOOD = "ifood", "iFood"

    class FormaPagamento(models.TextChoices):
        PIX = "pix", "Online Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao_entrega", "Cartao na entrega"

    class TipoColeta(models.TextChoices):
        ENTREGA = "entrega", "Entrega"
        RETIRADA = "retirada", "Retirada"

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        AGUARDANDO_APROVACAO = "aguardando_aprovacao", "Aguardando aprovação"
        NOVO = "novo", "Novo"
        EM_PREPARO = "em_preparo", "Em preparo"
        AGUARDANDO_ENTREGADOR = "aguardando_entregador", "Aguardando entregador"
        SAIU_ENTREGA = "saiu_entrega", "Saiu para entrega"
        FINALIZADO = "finalizado", "Finalizado"
        CANCELADO = "cancelado", "Cancelado"

    numero = models.PositiveIntegerField(unique=True, blank=True, null=True)
    nome_cliente = models.CharField(max_length=120)
    telefone = models.CharField(max_length=30)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    rua = models.CharField(max_length=180, blank=True)
    numero_endereco = models.CharField(max_length=20, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    cidade = models.CharField(max_length=120, blank=True, default="Rio Verde")
    estado = models.CharField(max_length=60, blank=True, default="GO")
    endereco_formatado = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    endereco = models.CharField(max_length=255)
    complemento = models.CharField(max_length=255, blank=True)
    lote_quadra = models.CharField(max_length=120, blank=True)
    ponto_referencia = models.CharField(max_length=255, blank=True)
    tipo_coleta = models.CharField(max_length=8, choices=TipoColeta.choices, default=TipoColeta.ENTREGA)
    icone_pedido = models.CharField(max_length=80, blank=True)
    forma_pagamento = models.CharField(max_length=20, choices=FormaPagamento.choices)
    enviar_talheres = models.BooleanField(default=True)
    canal = models.CharField(max_length=12, choices=Canal.choices, default=Canal.BALCAO)
    ifood = models.BooleanField(default=False)
    observacao_geral = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NOVO)
    distancia_km = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    valor_frete = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    total_sem_desconto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    promocao_descricao = models.CharField(max_length=120, blank=True)
    promocao_desconto = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    cupom = models.ForeignKey("Cupom", on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    cupom_codigo = models.CharField(max_length=40, blank=True)
    cupom_desconto = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    public_token = models.CharField(max_length=64, unique=True, blank=True, editable=False)
    checkout_key = models.CharField(max_length=80, unique=True, blank=True, null=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    producao_iniciada_em = models.DateTimeField(blank=True, null=True)
    entregador_solicitado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.numero or self.pk}"

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def google_maps_route_url(self):
        from .utils import build_google_maps_route_url

        return build_google_maps_route_url(self)

    @staticmethod
    def icon_path_for_number(numero):
        base_number = int(numero or 1)
        icon_index = ((base_number - 1) % PEDIDO_ICON_COUNT) + 1
        return f"{PEDIDO_ICON_FOLDER}/{icon_index}.svg"

    @property
    def icone_pedido_url(self):
        icon_path = self.icone_pedido or self.icon_path_for_number(self.numero or self.pk or 1)
        if icon_path.startswith("img/"):
            return f"/static/{icon_path}"
        return f"/static/img/{icon_path}"

    @property
    def is_retirada(self):
        return self.tipo_coleta == self.TipoColeta.RETIRADA

    @property
    def status_label_contextual(self):
        if self.status == self.Status.AGUARDANDO_ENTREGADOR:
            return "Aguardando coleta"
        if self.status == self.Status.SAIU_ENTREGA and self.is_retirada:
            return "Finalizado"
        if self.status == self.Status.FINALIZADO and self.is_retirada:
            return "Finalizado"
        if self.status == self.Status.FINALIZADO:
            return "Entregue"
        return self.get_status_display()

    @property
    def stage_labels(self):
        stages = [
            {"status": self.Status.NOVO, "number": "1", "label": "Pedido recebido"},
            {"status": self.Status.EM_PREPARO, "number": "2", "label": "Em produção"},
            {"status": self.Status.AGUARDANDO_ENTREGADOR, "number": "3", "label": "Aguardando coleta"},
        ]
        if self.is_retirada:
            return [*stages, {"status": self.Status.FINALIZADO, "number": "4", "label": "Finalizado"}]
        return [
            *stages,
            {"status": self.Status.SAIU_ENTREGA, "number": "4", "label": "Saiu para entrega"},
            {"status": self.Status.FINALIZADO, "number": "5", "label": "Entregue"},
        ]

    @property
    def item_type_counts(self):
        counts = {"pratos": 0, "adicionais": 0, "bebidas": 0}
        for item in self.itens.all():
            quantidade = max(item.quantidade or 0, 0)
            if item.prato_id:
                counts["pratos"] += quantidade
            elif item.adicional_id:
                counts["adicionais"] += quantidade
            elif item.bebida_id:
                counts["bebidas"] += quantidade
        return counts

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = Pedido.objects.filter(pk=self.pk).values_list("status", flat=True).first()

        entering_production = self.status == self.Status.EM_PREPARO and old_status != self.Status.EM_PREPARO
        production_start_changed = False
        if entering_production and not self.producao_iniciada_em:
            self.producao_iniciada_em = timezone.now()
            production_start_changed = True
        update_fields = kwargs.get("update_fields")
        if production_start_changed and update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"producao_iniciada_em"}

        if not self.numero:
            ultimo_numero = (
                Pedido.objects.exclude(numero__isnull=True).order_by("-numero").values_list("numero", flat=True).first()
            )
            self.numero = (ultimo_numero or 2239) + 1
        icon_changed = False
        if not self.icone_pedido:
            self.icone_pedido = self.icon_path_for_number(self.numero)
            icon_changed = True
        if icon_changed and update_fields is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"icone_pedido"}
        if not self.public_token:
            self.public_token = secrets.token_urlsafe(24)
        if self.pk and kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"atualizado_em"}
        super().save(*args, **kwargs)
        if entering_production:
            PedidoListaImpressao.objects.create(
                pedido=self,
                numero=self.numero,
                nome_cliente=self.nome_cliente,
                public_token=self.public_token,
            )


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    prato = models.ForeignKey(Prato, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    bebida = models.ForeignKey(Bebida, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    adicional = models.ForeignKey(Adicional, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    nome_prato_snapshot = models.CharField(max_length=120)
    variacao_nome_snapshot = models.CharField(max_length=120, blank=True)
    preco_snapshot = models.DecimalField(max_digits=8, decimal_places=2)
    quantidade = models.PositiveIntegerField(default=1)
    observacao = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "Item do pedido"
        verbose_name_plural = "Itens do pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.nome_prato_snapshot}"

    def save(self, *args, **kwargs):
        self.subtotal = Decimal(self.preco_snapshot) * self.quantidade
        super().save(*args, **kwargs)


class EnderecoCliente(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="enderecos")
    endereco = models.CharField(max_length=255)
    endereco_formatado = models.CharField(max_length=255, blank=True)
    rua = models.CharField(max_length=180, blank=True)
    numero_endereco = models.CharField(max_length=20, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    cidade = models.CharField(max_length=120, blank=True, default="Rio Verde")
    estado = models.CharField(max_length=60, blank=True, default="GO")
    complemento = models.CharField(max_length=255, blank=True)
    lote_quadra = models.CharField(max_length=120, blank=True)
    ponto_referencia = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    primeiro_uso_em = models.DateTimeField(blank=True, null=True)
    ultimo_uso_em = models.DateTimeField(blank=True, null=True)
    ultimo_pedido = models.ForeignKey(Pedido, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ultimo_uso_em", "endereco"]
        verbose_name = "Endereço do cliente"
        verbose_name_plural = "Endereços do cliente"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "endereco", "complemento", "lote_quadra", "ponto_referencia"],
                name="unique_cliente_endereco_usado",
            )
        ]

    def __str__(self):
        return self.endereco


class ClienteTokenConflito(models.Model):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        RESOLVIDO = "resolvido", "Resolvido"

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="conflitos_cliente")
    tokens = models.JSONField(default=list, blank=True)
    clientes = models.ManyToManyField(Cliente, related_name="conflitos_token")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ABERTO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Conflito de cliente por token"
        verbose_name_plural = "Conflitos de clientes por token"

    def __str__(self):
        return f"Conflito do pedido #{self.pedido.numero or self.pedido_id}"


class PedidoApiKey(models.Model):
    nome = models.CharField(max_length=120)
    prefixo = models.CharField(max_length=12, db_index=True)
    chave_hash = models.CharField(max_length=64, unique=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedido_api_keys",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_uso_em = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Chave da API de pedidos"
        verbose_name_plural = "Chaves da API de pedidos"

    def __str__(self):
        return f"{self.nome} ({self.prefixo}...)"

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()

    @classmethod
    def create_key(cls, nome, user=None):
        raw_key = f"pd_{secrets.token_urlsafe(32)}"
        instance = cls.objects.create(
            nome=nome,
            prefixo=raw_key[:12],
            chave_hash=cls.hash_key(raw_key),
            criado_por=user if getattr(user, "is_authenticated", False) else None,
        )
        return instance, raw_key

    @classmethod
    def authenticate(cls, raw_key):
        raw_key = str(raw_key or "").strip()
        if not raw_key:
            return None
        return cls.objects.filter(chave_hash=cls.hash_key(raw_key)).first()


class PedidoListaImpressao(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="lista_impressao")
    numero = models.PositiveIntegerField(blank=True, null=True)
    nome_cliente = models.CharField(max_length=120)
    public_token = models.CharField(max_length=64, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "id"]
        verbose_name = "Item da lista de impressao"
        verbose_name_plural = "Lista de impressao"

    def __str__(self):
        return f"Pedido #{self.numero or self.pedido_id} - {self.nome_cliente}"


class AccessEvent(models.Model):
    class EventType(models.TextChoices):
        MENU_VIEW = "menu_view", "Acesso ao cardapio"
        CART_VIEW = "cart_view", "Acesso ao carrinho"
        CHECKOUT_VIEW = "checkout_view", "Acesso ao caixa"
        PAGE_ACTIVE = "page_active", "Usuario ativo"
        ADD_TO_CART = "add_to_cart", "Item adicionado ao carrinho"
        REMOVE_FROM_CART = "remove_from_cart", "Item removido do carrinho"
        GO_TO_CHECKOUT = "go_to_checkout", "Avanco para caixa"
        CHECKOUT_SUBMIT = "checkout_submit", "Envio do caixa"
        PICKUP_SUBMIT = "pickup_submit", "Envio de retirada"
        ORDER_CREATED = "order_created", "Pedido criado"

    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    path = models.CharField(max_length=160, blank=True)
    session_key = models.CharField(max_length=40, db_index=True)
    item_type = models.CharField(max_length=20, blank=True)
    item_id = models.PositiveIntegerField(blank=True, null=True)
    cart_items_count = models.PositiveIntegerField(default=0)
    cart_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Evento de acesso"
        verbose_name_plural = "Eventos de acesso"

    def __str__(self):
        return f"{self.event_type} - {self.created_at:%d/%m/%Y %H:%M}"


class Cupom(models.Model):
    class TipoDesconto(models.TextChoices):
        PERCENTUAL = "percentual", "Percentual"
        VALOR_FIXO = "valor_fixo", "Valor fixo"

    codigo = models.CharField(max_length=40, unique=True)
    descricao = models.CharField(max_length=160, blank=True)
    ativo = models.BooleanField(default=True)
    tipo_desconto = models.CharField(max_length=20, choices=TipoDesconto.choices, default=TipoDesconto.VALOR_FIXO)
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    valor_minimo_pedido = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    uso_maximo_total = models.PositiveIntegerField(blank=True, null=True)
    data_inicio = models.DateTimeField(blank=True, null=True)
    data_fim = models.DateTimeField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ativo", "codigo"]

    def __str__(self):
        return self.codigo


class FaixaFrete(models.Model):
    class Tipo(models.TextChoices):
        ATE = "ate", "Até"
        ACIMA = "acima", "Acima de"

    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ATE)
    km_limite = models.DecimalField(max_digits=6, decimal_places=2)
    valor = models.DecimalField(max_digits=8, decimal_places=2)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "km_limite", "id"]
        verbose_name = "Faixa de frete"
        verbose_name_plural = "Faixas de frete"

    def __str__(self):
        prefixo = "Até" if self.tipo == self.Tipo.ATE else "Acima de"
        return f"{prefixo} {self.km_limite} km - R$ {self.valor}"


class ConfiguracaoEntrega(models.Model):
    horario_abertura = models.TimeField(blank=True, null=True)
    horario_fechamento = models.TimeField(blank=True, null=True)
    origem_endereco = models.CharField(max_length=255, blank=True)
    origem_latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    origem_longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    google_maps_api_key = models.CharField(max_length=255, blank=True)
    google_maps_language = models.CharField(max_length=20, blank=True, default="pt-BR")
    google_maps_region = models.CharField(max_length=10, blank=True, default="BR")
    whatsapp_numero = models.CharField(max_length=24, blank=True)
    pix_chave = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração de entrega"
        verbose_name_plural = "Configuracoes de entrega"

    def __str__(self):
        return "Configuração de entrega"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def google_maps_api_key_effective(self):
        return (self.google_maps_api_key or "").strip() or getattr(settings, "GOOGLE_MAPS_API_KEY", "")

    @property
    def google_maps_language_effective(self):
        return (self.google_maps_language or "").strip() or getattr(settings, "GOOGLE_MAPS_LANGUAGE", "pt-BR")

    @property
    def google_maps_region_effective(self):
        return (self.google_maps_region or "").strip() or getattr(settings, "GOOGLE_MAPS_REGION", "BR")

    @classmethod
    def get_solo(cls):
        instance = cls.objects.order_by("pk").first()
        if instance:
            if instance.pk != 1:
                instance.pk = 1
                instance.save()
            return instance
        return cls.objects.create(pk=1)
