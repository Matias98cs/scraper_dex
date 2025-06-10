import os
import json
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from scrapers.models import (
    Brand, Category, Product, Page, ProductPage,
    Pricing, ProductQuota, Size, ProductSize
)

def parse_decimal(s):
    if not s or s.strip().upper() in ("N/A", ""):
        return None
    clean = s.replace('$', '').replace('.', '').strip().replace('%', '')
    if ',' in clean and clean.count(',') == 1:
        clean = clean.replace(',', '.')
    try:
        return Decimal(clean)
    except:
        return None

def parse_bool(val):
    if isinstance(val, bool):
        return val
    val = str(val).strip().lower()
    return val in ["true", "1", "sí", "si", "gratis", "envío gratis"]

class Command(BaseCommand):
    help = "Importa productos desde JSON de Grid para page_id=7"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "json_pruebas", "grid.json"),
            help="Ruta al archivo JSON"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra todos los registros relacionados con la página id=7 antes de cargar"
        )

    def handle(self, *args, **options):
        path = options["file"]
        if not os.path.exists(path):
            raise CommandError(f"No encontré el archivo JSON: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CommandError(f"Error leyendo JSON: {e}")

        with transaction.atomic():
            try:
                page_obj = Page.objects.get(pk=6)
            except Page.DoesNotExist:
                raise CommandError("No existe la página con id=6 (Grid)")

            if options["clear"]:
                self.stdout.write("🧹 Borrando registros relacionados con page_id=7…")
                ProductSize.objects.filter(product__pages__page=page_obj).delete()
                ProductQuota.objects.filter(product__pages__page=page_obj).delete()
                Pricing.objects.filter(page=page_obj).delete()
                ProductPage.objects.filter(page=page_obj).delete()
                Product.objects.filter(pages__page=page_obj).delete()

            now = timezone.now()
            total = 0

            print('Cantidad de productos: ', len(data))
            
            for item in data:
                model_code = item.get("model_id")
                if not model_code:
                    continue

                if Product.objects.filter(model_code=model_code, pages__page=page_obj).exists():
                    continue

                brand_obj, _ = Brand.objects.get_or_create(
                    name=(item.get("marca") or "").strip()
                )
                category_obj, _ = Category.objects.get_or_create(
                    name=(item.get("categoria") or "").strip()
                )

                product = Product.objects.create(
                    name=(item.get("nombre") or "").strip(),
                    brand=brand_obj,
                    category=category_obj,
                    product_class=(item.get("clase_de_producto") or "").strip(),
                    model_code=model_code,
                    sku=item.get("sku"),
                    image_url=item.get("imagen_url"),
                    link=item.get("link"),
                    created_at=now,
                    updated_at=now,
                    provider_code=model_code
                )

                ProductPage.objects.create(
                    product=product,
                    page=page_obj,
                    cuotas=item.get("cuotas"),
                    payment_info="",
                    shipping_info=item.get("envio_gratis") or ""
                )

                Pricing.objects.create(
                    product=product,
                    page=page_obj,
                    price_current=parse_decimal(item.get("precio")),
                    price_prev=parse_decimal(item.get("precio_anterior")),
                    discount=parse_decimal(item.get("descuento")),
                    free_shipping=parse_bool(item.get("envio_gratis")),
                    currency="ARS",
                    recorded_at=now
                )

                for size in item.get("disponibles", []):
                    size_obj, _ = Size.objects.get_or_create(name=size)
                    ProductSize.objects.create(product=product, size=size_obj, available=1)
                for size in item.get("no_disponibles", []):
                    size_obj, _ = Size.objects.get_or_create(name=size)
                    ProductSize.objects.create(product=product, size=size_obj, available=0)

                total += 1

            self.stdout.write(self.style.SUCCESS(f"✔️ Importados {total} productos para Grid (page_id=7)."))
