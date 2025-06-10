from django.core.management.base import BaseCommand
from scrapers.models import Product, ProductPage, CodesDexter

class Command(BaseCommand):
    help = "Actualiza el provider_code de Product buscando por model_code en CodesDexter.dexter_code (solo pages 1, 9, 10)"

    def handle(self, *args, **options):
        page_ids = [1, 9, 10]
        productos = Product.objects.filter(pages__page_id__in=page_ids).distinct()

        total_revisados = 0
        total_actualizados = 0

        for producto in productos:
            total_revisados += 1
            model_code = (producto.model_code or "").strip()
            if not model_code:
                continue

            try:
                code = CodesDexter.objects.get(dexter_code=model_code)
                if producto.provider_code != code.provider_code:
                    producto.provider_code = code.provider_code
                    producto.save(update_fields=["provider_code"])
                    total_actualizados += 1
            except CodesDexter.DoesNotExist:
                continue

        self.stdout.write(self.style.SUCCESS(
            f"✔️ Revisados {total_revisados} productos. Se actualizaron {total_actualizados} provider_code desde CodesDexter."
        ))
