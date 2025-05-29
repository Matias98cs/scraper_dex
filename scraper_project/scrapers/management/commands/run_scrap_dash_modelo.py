from django.core.management.base import BaseCommand
import pandas as pd
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re

EXCEL_PATHS = [
    "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_combinado_20250519_145736.xlsx"
]

WAIT_TIME = 3
# ────────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Procesa EXCELs de Dash y extrae el código de modelo'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Iniciando navegador en modo headless...")
        # Configurar Chrome en modo headless
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        code_pattern = re.compile(r'Código[:\s]*([A-Za-z0-9\-]+)', re.IGNORECASE)

        for path in EXCEL_PATHS:
            self.stdout.write(f"➡ Procesando {path}...")
            try:
                df = pd.read_excel(path)
            except Exception as e:
                self.stderr.write(f"❌ Error leyendo {path}: {e}")
                continue

            if 'modelo' not in df.columns:
                df['modelo'] = ''
            else:
                df['modelo'] = df['modelo'].fillna('').astype(object)

            for idx, url in df['link'].items():
                modelo_val = ''
                if not isinstance(url, str) or not url.startswith('http'):
                    self.stdout.write(f"  ⚠ Fila {idx}: URL inválida, saltando...")
                    continue

                try:
                    driver.get(url)
                    time.sleep(WAIT_TIME)
                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    # Buscar en tabla de especificaciones
                    for tr in soup.select('table.vtex-store-components-3-x-specificationsTable tbody tr'):
                        prop_td = tr.select_one('td.vtex-store-components-3-x-specificationItemProperty')
                        if prop_td and prop_td.get('data-specification', '').strip().lower() == 'proveedor':
                            spec_td = tr.select_one('td.vtex-store-components-3-x-specificationItemSpecifications')
                            if spec_td:
                                modelo_val = spec_td.get('data-specification', spec_td.get_text(strip=True)).strip()
                            break

                    # Si no encontrado, buscar en descripción
                    if not modelo_val:
                        desc_div = soup.select_one('div.dash-theme-6-x-DescripcionProd div')
                        if desc_div:
                            m = code_pattern.search(desc_div.get_text())
                            if m:
                                modelo_val = m.group(1).strip()

                    df.at[idx, 'modelo'] = modelo_val or ''
                    if modelo_val:
                        self.stdout.write(f"  Fila {idx}: modelo {modelo_val}")
                    else:
                        self.stdout.write(f"  Fila {idx}: sin modelo")

                except Exception as e:
                    self.stderr.write(f"  ⚠ Error en {url}: {e}")
                    df.at[idx, 'modelo'] = 'ERROR'

            salida = re.sub(r'\.xlsx?$', '_con_detalle.xlsx', path, flags=re.IGNORECASE)
            try:
                df.to_excel(salida, index=False)
                self.stdout.write(f"✅ Guardado → {salida}")
            except Exception as e:
                self.stderr.write(f"❌ No se pudo guardar {salida}: {e}")

        driver.quit()
        self.stdout.write(self.style.SUCCESS('🚀 Procesamiento modelo terminado.'))
