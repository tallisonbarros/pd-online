from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageOps

from pedidos.image_optimization import optimized_menu_image_path
from pedidos.models import Adicional, Bebida, Prato


STATIC_IMAGE_TARGETS = [
    ("img/icon_marmita_selada.png", "img/optimized/icon_marmita_selada.webp", (160, 160), 78),
    ("img/promocao-4-mais-1.png", "img/optimized/promocao-4-mais-1.webp", (1200, 900), 80),
]


class Command(BaseCommand):
    help = "Gera imagens WebP leves para o cardapio sem sobrescrever os arquivos originais."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        optimized = 0
        skipped = 0
        failed = 0

        sources = [
            ("prato", Prato.objects.exclude(imagem="").exclude(imagem__isnull=True)),
            ("adicional", Adicional.objects.exclude(imagem="").exclude(imagem__isnull=True)),
            ("bebida", Bebida.objects.exclude(imagem="").exclude(imagem__isnull=True)),
        ]

        for label, queryset in sources:
            for item in queryset:
                before = None
                try:
                    before = Path(item.imagem.path)
                except (ValueError, NotImplementedError):
                    failed += 1
                    self.stderr.write(f"{label} #{item.pk}: imagem sem caminho local")
                    continue

                if dry_run:
                    self.stdout.write(f"{label} #{item.pk}: geraria otimizacao para {before.name}")
                    skipped += 1
                    continue

                output_path = optimized_menu_image_path(item.imagem)
                if output_path:
                    optimized += 1
                    self.stdout.write(f"{label} #{item.pk}: {before.name} -> {output_path.name}")
                else:
                    failed += 1
                    self.stderr.write(f"{label} #{item.pk}: falha ao otimizar {before.name}")

        for source_name, target_name, max_size, quality in STATIC_IMAGE_TARGETS:
            source_path = Path(settings.BASE_DIR) / "static" / source_name
            target_path = Path(settings.BASE_DIR) / "static" / target_name
            if not source_path.exists():
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(f"static: geraria {target_name}")
                skipped += 1
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with Image.open(source_path) as image:
                    image = ImageOps.exif_transpose(image)
                    if image.mode not in ("RGB", "RGBA"):
                        image = image.convert("RGB")
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    image.save(target_path, "WEBP", quality=quality, method=6)
                optimized += 1
                self.stdout.write(f"static: {source_name} -> {target_name}")
            except Exception as exc:
                failed += 1
                self.stderr.write(f"static: falha ao otimizar {source_name}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Otimizacao concluida. Geradas/verificadas: {optimized} | Puladas: {skipped} | Falhas: {failed}"
            )
        )
