import json
import re
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.management.base import BaseCommand
from scrapers.models import (
    Brand, Category, Page, Product,
    Pricing, ProductQuota, Size, ProductSize
)
import time
from pathlib import Path
from django.conf import settings


BASE_DIR = Path(settings.BASE_DIR)

JSON_FILES = [
    BASE_DIR / 'outputs' / 'dash'         / 'productos_dash_more.json',
    BASE_DIR / 'outputs' / 'dexter'       / 'productos_dexter_20250523_145751_combinado.json',
    BASE_DIR / 'outputs' / 'solodeportes' / 'productos_solodeportes_20250522_225533_combinado.json',
    BASE_DIR / 'outputs' / 'stock_center' / 'productos_stockcenter_20250523_163238_combinado.json',
    BASE_DIR / 'outputs' / 'solourbano'   / 'productos_solourbano_20250522_174102_combinado.json',
]


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

class Command(BaseCommand):
    help = 'Importa y cuenta productos y pricings nuevos por JSON, e inserta cuotas y talles'

    def handle(self, *args, **opts):
        otro_brand, _ = Brand.objects.get_or_create(name='otro')
        otro_cat, _   = Category.objects.get_or_create(name='otro')
        now = timezone.now()

        for path in JSON_FILES:
            try:
                data = json.load(open(path, encoding='utf-8'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error leyendo {path}: {e}'))
                continue

            prod_created = 0
            pricing_created = 0
            total = len(data)
            self.stdout.write(f'→ Procesando {total} registros de {path}')

            last_log = time.time()
            processed = 0

            with transaction.atomic():
                pending_sizes = []

                for obj in data:
                    processed += 1
                    if time.time() - last_log >= 20:
                        pct = processed / total * 100
                        self.stdout.write(f'  {processed}/{total} registros procesados ({pct:.1f}%)')
                        last_log = time.time()

                    page = Page.objects.filter(name=obj.get('nombre_pagina','').strip()).first()
                    if not page:
                        continue

                    raw_brand = obj.get('marca','').strip()
                    brand = Brand.objects.get_or_create(
                        name=raw_brand.lower()
                    )[0] if raw_brand else otro_brand

                    raw_cat = obj.get('categoria','').strip()
                    category = Category.objects.get_or_create(
                        name=raw_cat.lower()
                    )[0] if raw_cat else otro_cat

                    raw_sku = obj.get('sku','').strip().upper()
                    sku = raw_sku if raw_sku and raw_sku!='N/A' else None
                    lookup = {'sku':sku} if sku else {'link':obj.get('link','').strip()}

                    prod, was_created = Product.objects.get_or_create(
                        **lookup,
                        defaults={'created_at':now, 'updated_at':now, 'brand':brand, 'category':category}
                    )
                    if was_created:
                        prod_created += 1

                    price_current = parse_decimal(obj.get('precio',''))
                    if price_current is None:
                        price_current = Decimal('0.00')
                    env = obj.get('envio_gratis','')
                    free_shipping = env if isinstance(env,bool) else str(env).lower() in ('sí','si','yes','true')
                    pricing, pricing_new = Pricing.objects.update_or_create(
                        product=prod, page=page,
                        defaults={
                            'price_current': price_current,
                            'price_prev':    parse_decimal(obj.get('precio_anterior','')),
                            'discount':      parse_decimal(obj.get('descuento','')),
                            'free_shipping': free_shipping,
                            'currency':      'ARS',
                            'recorded_at':   now,
                        }
                    )
                    if pricing_new or was_created:
                        pricing_created += 1

                    cuotas_txt = obj.get('cuotas','')
                    m = re.search(r'(\d+)', cuotas_txt)
                    if m:
                        count = int(m.group(1))
                        monto_match = re.search(r'de\s*\$?([\d\.,]+)', cuotas_txt)
                        price_per = parse_decimal(monto_match.group(1)) if monto_match else Decimal('0')
                        ProductQuota.objects.update_or_create(
                            product=prod, page=page, payment_method='default',
                            defaults={
                                'quota_count':     count,
                                'price_per_quota': price_per,
                                'interest_free':   'sin interés' in cuotas_txt.lower()
                            }
                        )

                    for size_str in obj.get('disponible',[]) or []:
                        sz, _ = Size.objects.get_or_create(name=size_str)
                        pending_sizes.append(ProductSize(
                            product=prod, size=sz, available=1, country='AR'))
                    for size_str in obj.get('no_disponible',[]) or []:
                        sz, _ = Size.objects.get_or_create(name=size_str)
                        pending_sizes.append(ProductSize(
                            product=prod, size=sz, available=0, country='AR'))

                ProductSize.objects.bulk_create(
                    pending_sizes, ignore_conflicts=True
                )

            self.stdout.write(self.style.SUCCESS(
                f'{path} → {prod_created} productos nuevos, {pricing_created} pricings nuevos.'
            ))

        self.stdout.write(self.style.SUCCESS('✅ Importación completa de todos los JSON.'))