import os
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from scrapers.models import (
    Brand, Category, Product, Page, ProductPage,
    Pricing, ProductQuota, Size, ProductSize
)
from django.db import transaction
from decimal import Decimal, InvalidOperation


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
    if val in ["true", "1", "sí", "si", "gratis", "envío gratis"]:
        return True
    return False


class Command(BaseCommand):
    help = "Importa productos desde json_pruebas/moov.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "json_pruebas", "moov.json"),
            help="Ruta al archivo JSON"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra todos los registros relacionados con la página id=10 antes de cargar"
        )

    def handle(self, *args, **options):
        path = options["file"]
        if not os.path.exists(path):
            raise CommandError(f"No encontré el archivo JSON: {path}")

        now = timezone.now()

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CommandError(f"Error leyendo JSON: {e}")
        
        with transaction.atomic():
            try:
                page_obj = Page.objects.get(pk=10)
            except Page.DoesNotExist:
                raise CommandError("No existe la página con id=10")
            
            if options["clear"]:
                self.stdout.write("🧹 Borrando registros relacionados con page_id=10…")
                ProductSize.objects.filter(product__pages__page=page_obj).delete()
                ProductQuota.objects.filter(product__pages__page=page_obj).delete()
                Pricing.objects.filter(page=page_obj).delete()
                ProductPage.objects.filter(page=page_obj).delete()
                Product.objects.filter(pages__page=page_obj).delete()
            
            print('Cantidad de productos: ', len(data))

            total = 0
            for item in data:
                model_code = item.get("model_id")
                if not model_code:
                    continue

                brand_obj, _ = Brand.objects.get_or_create(
                    name=(item.get("marca") or "").strip()
                )
                category_obj, _ = Category.objects.get_or_create(
                    name=(item.get("categoria") or "").strip()
                )


                producto_existente = Product.objects.filter(
                    model_code=model_code
                ).filter(pages__page=page_obj).first()

                if producto_existente:
                    continue


                producto = Product.objects.create(
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
                    product=producto,
                    page=page_obj,
                    cuotas=item.get("cuotas"),
                    payment_info=item.get("payment_info"),
                    shipping_info=item.get("shipping_info")
                )

                Pricing.objects.create(
                    product=producto,
                    page=page_obj,
                    price_current=parse_decimal(item.get("precio")),
                    price_prev=parse_decimal(item.get("precio_anterior")),
                    discount=parse_decimal(item.get("descuento")),
                    free_shipping=parse_bool(item.get("envio_gratis")),
                    currency=item.get("moneda", ""),
                    recorded_at=now
                )

                cuotas_str = item.get("cuotas")
                if cuotas_str:
                    # TODO: implementar parseo de cuotas:
                    # número de cuotas, monto por cuota, interés, método de pago
                    pass

                for size_name in item.get("disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(
                        product=producto,
                        size=size_obj,
                        available=1
                    )
                for size_name in item.get("no_disponible", []):
                    size_obj, _ = Size.objects.get_or_create(name=size_name)
                    ProductSize.objects.create(
                        product=producto,
                        size=size_obj,
                        available=0
                    )

                total += 1

            self.stdout.write(self.style.SUCCESS(f"✔️ Importados {total} productos."))
