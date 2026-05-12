from decimal import Decimal
import secrets

from django.db import models
from django.conf import settings


class Prato(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    imagem = models.ImageField(upload_to="pratos/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
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


class Bebida(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    imagem = models.ImageField(upload_to="bebidas/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Adicional(models.Model):
    nome = models.CharField(max_length=120)
    descricao = models.CharField(max_length=255, blank=True)
    imagem = models.ImageField(upload_to="adicionais/", blank=True, null=True)
    preco = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Pedido(models.Model):
    class FormaPagamento(models.TextChoices):
        PIX = "pix", "Online Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao_entrega", "Cartao na entrega"

    class Status(models.TextChoices):
        AGUARDANDO_APROVACAO = "aguardando_aprovacao", "Aguardando aprovação"
        NOVO = "novo", "Novo"
        EM_PREPARO = "em_preparo", "Em preparo"
        SAIU_ENTREGA = "saiu_entrega", "Saiu para entrega"
        FINALIZADO = "finalizado", "Finalizado"
        CANCELADO = "cancelado", "Cancelado"

    numero = models.PositiveIntegerField(unique=True, blank=True, null=True)
    nome_cliente = models.CharField(max_length=120)
    telefone = models.CharField(max_length=30)
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
    forma_pagamento = models.CharField(max_length=20, choices=FormaPagamento.choices)
    enviar_talheres = models.BooleanField(default=True)
    observacao_geral = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOVO)
    distancia_km = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    valor_frete = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    public_token = models.CharField(max_length=64, unique=True, blank=True, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

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

    def save(self, *args, **kwargs):
        if not self.numero:
            ultimo_numero = (
                Pedido.objects.exclude(numero__isnull=True).order_by("-numero").values_list("numero", flat=True).first()
            )
            self.numero = (ultimo_numero or 2239) + 1
        if not self.public_token:
            self.public_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    prato = models.ForeignKey(Prato, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    bebida = models.ForeignKey(Bebida, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    adicional = models.ForeignKey(Adicional, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_pedido")
    nome_prato_snapshot = models.CharField(max_length=120)
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
