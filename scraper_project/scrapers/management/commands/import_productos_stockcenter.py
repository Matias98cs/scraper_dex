import os
import json
from decimal import Decimal, InvalidOperation
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
            return Decimal(str(raw_discount))
        except:
            pass
    if original_price and price and original_price > price:
        try:
            return ((original_price - price) / original_price * 100).quantize(Decimal("0.01"))
        except:
            pass
    return None

class Command(BaseCommand):
    help = "Importa productos desde productos_stockcenter_*.json para page_id=9 (Stock Center)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "json_pruebas", "productos_stockcenter_20250530_145659_combinado.json"),
            help="Ruta al archivo JSON"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra todos los registros relacionados con la página id=9 antes de cargar"
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
                page_obj = Page.objects.get(pk=9)
            except Page.DoesNotExist:
                raise CommandError("No existe la página con id=9 (Stock Center)")

            if options["clear"]:
                self.stdout.write("🧹 Borrando registros relacionados con page_id=9…")
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

                brand_name = (item.get("marca") or "").strip()
                if brand_name.upper() in ("N/A", ""):
                    brand_obj = Brand.objects.get(name__iexact="otro")
                else:
                    brand_obj, _ = Brand.objects.get_or_create(name=brand_name)

                category_obj, _ = Category.objects.get_or_create(
                    name=(item.get("categoria") or "").strip()
                )

                producto_existente = Product.objects.filter(
                    model_code=model_code
                ).filter(pages__page=page_obj).first()

                if producto_existente:
                    continue
                
                product = Product.objects.filter(model_code=model_code).first()
                if not product:
                    product = Product.objects.create(
                        name=(item.get("nombre") or "").strip(),
                        brand=brand_obj,
                        category=category_obj,
                        product_class=(item.get("clase_de_producto") or "").strip(),
                        model_code=model_code,
                        sku=model_code,
                        image_url=item.get("imagen_url"),
                        link=item.get("link") or "https://stockcenter.com.ar/",
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
                        provider_code=model_code
                    )

                ProductPage.objects.create(
                    product=product,
                    page=page_obj,
                    cuotas=None,
                    payment_info="",
                    shipping_info=""
                )

                price = parse_decimal(item.get("precio"))
                original_price = parse_decimal(item.get("precio_anterior"))
                discount = get_discount(item.get("descuento"), price, original_price)

                Pricing.objects.create(
                    product=product,
                    page=page_obj,
                    price_current=price,
                    price_prev=original_price,
                    discount=discount,
                    free_shipping=False,
                    currency="ARS",
                    recorded_at=item.get("created") or timezone.now()
                )

                for size_name in item.get("available_sizes", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=1)
                for size_name in item.get("unavailable_sizes", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(product=product, size=size_obj, available=0)

                total += 1

            self.stdout.write(self.style.SUCCESS(f"✔️ Importados {total} productos para Stock Center (page_id=9)."))