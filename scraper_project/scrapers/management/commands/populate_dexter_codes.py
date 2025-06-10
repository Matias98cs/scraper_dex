import os
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from scrapers.models import CodesDexter

class Command(BaseCommand):
    help = "Importa los codigos desde el Excel en dexter_codes/codigos_dexter.xlsx"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Si se pasa, borra todos los registros antes de cargar"
        )
        parser.add_argument(
            "--file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "dexter_codes", "codigos_dexter.xlsx"),
            help="Ruta al archivo Excel"
        )

    def handle(self, *args, **options):
        path = options["file"]

        if not os.path.exists(path):
            raise CommandError(f"No encontré el archivo: {path}")

        if options["clear"]:
            self.stdout.write("🔄 Borrando registros existentes...")
            CodesDexter.objects.all().delete()

        try:
            df = pd.read_excel(path, sheet_name="codigos", engine="openpyxl")
        except Exception as e:
            raise CommandError(f"Error leyendo Excel: {e}")

        total = 0
        for _, row in df.iterrows():
            marca = row.get("MARCA", None)
            prov = row.get("CODIGO PROVEEDOR", None)
            dex = row.get("CODIGO GRUPO DEXTER", None)

            if pd.isna(marca) and pd.isna(prov) and pd.isna(dex):
                continue

            CodesDexter.objects.create(
                brand=str(marca).strip() if not pd.isna(marca) else None,
                provider_code=str(prov).strip() if not pd.isna(prov) else None,
                dexter_code=str(dex).strip() if not pd.isna(dex) else None,
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(f"✔️ Importados {total} códigos."))
