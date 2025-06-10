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
    clean = s.replace('$','').replace('.','').strip().replace('%','')
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
    help = "Importa productos desde JSON de Dash para page_id=2"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "json_pruebas", "dash_more_threads_1.json"),
            help="Ruta al archivo JSON"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra todos los registros relacionados con la página id=2 antes de cargar"
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
                page_obj = Page.objects.get(pk=2)
            except Page.DoesNotExist:
                raise CommandError("No existe la página con id=2 (Dash)")

            if options["clear"]:
                self.stdout.write("🧹 Borrando registros relacionados con page_id=2…")
                ProductSize.objects.filter(product__pages__page=page_obj).delete()
                ProductQuota.objects.filter(product__pages__page=page_obj).delete()
                Pricing.objects.filter(page=page_obj).delete()
                ProductPage.objects.filter(page=page_obj).delete()
                Product.objects.filter(pages__page=page_obj).delete()

            total = 0
            for item in data:
                model_code = item.get("modelo_id")
                if not model_code:
                    continue

                brand_obj, _ = Brand.objects.get_or_create(
                    name=(item.get("marca") or "").strip()
                )
                category_obj, _ = Category.objects.get_or_create(
                    name=(item.get("categoria") or "").strip()
                )

                price = parse_decimal(item.get("precio"))
                original_price = parse_decimal(item.get("precio_anterior"))
                discount = get_discount(item.get("descuento"), price, original_price)


                producto_existente = Product.objects.filter(
                    model_code=model_code
                ).filter(pages__page=page_obj).first()

                if producto_existente:
                    continue

                product = Product.objects.create(
                    name=(item.get("nombre") or "").strip(),
                    brand=brand_obj,
                    category=category_obj,
                    product_class=(item.get("clase_de_producto") or "").strip(),
                    model_code=model_code,
                    sku=item.get("sku"),
                    image_url=item.get("imagen_url"),
                    link=item.get("link"),
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                    provider_code=item.get("modelo_id")
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
                    price_current=price,
                    price_prev=original_price,
                    discount=discount,
                    free_shipping=parse_bool(item.get("envio_gratis")),
                    currency="ARS",
                    recorded_at=timezone.now()
                )

                for size_name in item.get("disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=1)
                for size_name in item.get("no_disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=0)

                for cuota in item.get("financiacion", []):
                    if not cuota.get("num_cuotas") or not cuota.get("precio_por_cuota"):
                        continue
                    ProductQuota.objects.create(
                        product=product,
                        page=page_obj,
                        payment_method=cuota.get("banco") or "",
                        quota_count=int(cuota.get("num_cuotas")),
                        price_per_quota=Decimal(str(cuota.get("precio_por_cuota"))),
                        interest_free=parse_bool(cuota.get("sin_interes"))
                    )

                total += 1

            self.stdout.write(self.style.SUCCESS(f"✔️ Importados {total} productos para Dash (page_id=2)."))
