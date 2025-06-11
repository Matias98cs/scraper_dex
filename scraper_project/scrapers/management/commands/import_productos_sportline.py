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
    if not s or s.strip().upper() in ("N/A", "", "Sin precio anterior", "Sin descuento"):
        return None
    clean = s.replace('$', '').replace('.', '').strip().replace('%', '').replace('\xa0', '').replace(',', '.')
    try:
        return Decimal(clean)
    except:
        return None

def parse_bool(val):
    if isinstance(val, bool):
        return val
    val = str(val).strip().lower()
    return val in ["true", "1", "sí", "si", "gratis", "envío gratis"]

def get_discount(raw_discount, price, original_price):
    if raw_discount:
        try:
            return Decimal(str(raw_discount).replace('%', '').replace('-', ''))
        except:
            pass
    if original_price and price and original_price > price:
        try:
            return ((original_price - price) / original_price * 100).quantize(Decimal("0.01"))
        except:
            pass
    return None

class Command(BaseCommand):
    help = "Importa productos desde JSON de Sportline para page_id=4"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "json_pruebas", "productos_sportline_20250611_191349_combinado.json"),
            help="Ruta al archivo JSON con los productos de Sportline"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra todos los registros relacionados con la página id=4 antes de cargar"
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
                page_obj = Page.objects.get(pk=4)
            except Page.DoesNotExist:
                raise CommandError("No existe la página con id=4 (Sportline)")

            if options["clear"]:
                self.stdout.write("Borrando registros relacionados con page_id=4…")
                ProductSize.objects.filter(product__pages__page=page_obj).delete()
                ProductQuota.objects.filter(product__pages__page=page_obj).delete()
                Pricing.objects.filter(page=page_obj).delete()
                ProductPage.objects.filter(page=page_obj).delete()
                Product.objects.filter(pages__page=page_obj).delete()

            total = 0
            now = timezone.now()

            self.stdout.write(f'Cantidad de productos a importar: {len(data)}')

            for item in data:
                model_code = item.get("id_producto")
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

                price = parse_decimal(item.get("precio"))
                if not price:
                    continue

                original_price = parse_decimal(item.get("precio_anterior"))
                discount = get_discount(item.get("descuento"), price, original_price)

                product = Product.objects.create(
                    name=(item.get("nombre") or "").strip(),
                    brand=brand_obj,
                    category=category_obj,
                    product_class=(item.get("clase_de_producto") or "").strip(),
                    model_code=model_code,
                    sku=item.get("sku") or model_code,
                    image_url=item.get("imagen_url"),
                    link=item.get("link"),
                    created_at=now,
                    updated_at=now,
                    provider_code=model_code
                )

                ProductPage.objects.create(
                    product=product,
                    page=page_obj,
                    cuotas=item.get("cuotas") or "",
                    payment_info="",
                    shipping_info=item.get("envio_gratis") or ""
                )

                Pricing.objects.create(
                    product=product,
                    page=page_obj,
                    price_current=price,
                    price_prev=original_price,
                    discount=discount,
                    free_shipping=parse_bool(item.get("envio_gratis")),
                    currency="ARS",
                    recorded_at=now
                )

                for size_name in item.get("disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=1)
                for size_name in item.get("no_disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=0)

                total += 1

            self.stdout.write(self.style.SUCCESS(
                f"✔️ Importados {total} productos para Sportline (page_id=4)."
            ))
