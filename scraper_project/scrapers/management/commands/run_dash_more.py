import json
import re
import logging
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

JSON_PATH = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_20250522_153333_combinado.json"
OUTPUT_JSON = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_more.json"

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--headless',
            action='store_true',
            help='Ejecutar Chrome en modo headless'
        )

    def handle(self, *args, **options):
        headless = options['headless']

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S"
        )

        with open(JSON_PATH, encoding="utf-8") as f:
            items = json.load(f)
        logger.info(f"Cargados {len(items)} productos desde {JSON_PATH}")

        chrome_opts = Options()
        if headless:
            chrome_opts.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_opts)

        def extraer_modelo_id(soup):
            cell = soup.find("td", {"data-specification": "Proveedor"})
            if cell:
                value = cell.find_next_sibling("td")
                if value:
                    return value.get_text(strip=True)
            desc = soup.select_one("div.dash-theme-6-x-DescripcionProd div")
            if desc:
                text = desc.get_text(separator=" ", strip=True)
                m = re.search(r"[Cc]ódigo[:\s]*([\w\/\-\d]+)", text)
                if m:
                    return m.group(1)

            return "N/A"

        def extraer_talles(soup):
            disponibles, no_disponibles = [], []
            items_btn = soup.select(".vtex-store-components-3-x-skuSelectorItem")
            for btn in items_btn:
                txt = btn.select_one(".vtex-store-components-3-x-skuSelectorItemTextValue")
                if not txt:
                    continue
                talla = txt.get_text(strip=True)
                if btn.find("div", class_="vtex-store-components-3-x-diagonalCross"):
                    no_disponibles.append(talla)
                else:
                    disponibles.append(talla)
            return disponibles, no_disponibles

        resultados = []
        for idx, item in enumerate(items, start=1):
            url = item.get("link")
            logger.info(f"[{idx}/{len(items)}] Abriendo {url}")
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "div.vtex-store-components-3-x-specificationsTableContainer, div.dash-theme-6-x-DescripcionProd"))
                )
            except Exception:
                logger.warning("  No se encontró sección de especificaciones ni descripción.")

            soup = BeautifulSoup(driver.page_source, "html.parser")

            modelo = extraer_modelo_id(soup)
            disp, nodisp = extraer_talles(soup)

            item["modelo_id"]     = modelo
            item["disponible"]    = disp
            item["no_disponible"] = nodisp

            logger.info(f"  → Modelo: {modelo}")
            logger.info(f"  → Disponibles: {disp}")
            logger.info(f"  → No disponibles: {nodisp}")
            logger.info("----------------------------------------")

            resultados.append(item)

        driver.quit()

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as out_f:
            json.dump(resultados, out_f, ensure_ascii=False, indent=2)
        logger.info(f"Resultados guardados en {OUTPUT_JSON}")
