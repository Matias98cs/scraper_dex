import json
import logging
import time
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

JSON_PATH   = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/solourbano/productos_solourbano_20250601_133731_combinado.json"
OUTPUT_JSON = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/solourbano/productos_solourbano_20250601_133731_more.json"

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
        chrome_opts.add_argument("--start-maximized")
        driver = webdriver.Chrome(options=chrome_opts)
        driver.implicitly_wait(1)

        def extraer_talles(soup):
            disponibles, no_disponibles = [], []
            script_text = ""
            for tag in soup.find_all("script"):
                if tag.string and "jsonConfig" in tag.string:
                    script_text = tag.string
                    break

            if script_text:
                m = re.search(r'"jsonConfig"\s*:\s*(\{.*?\})\s*,\s*"jsonSwatchConfig"', script_text, re.DOTALL)
                if m:
                    try:
                        cfg = json.loads(m.group(1))
                        atributos = cfg.get("attributes", {})
                        for attr_id, attr_data in atributos.items():
                            if attr_data.get("code") == "talle":
                                for option in attr_data.get("options", []):
                                    label = option.get("label")
                                    if option.get("products"):
                                        disponibles.append(label)
                                    else:
                                        no_disponibles.append(label)
                                break
                    except Exception:
                        pass

            return disponibles, no_disponibles

        def extraer_cuotas_bancos(soup):
            resultados = []
            go_tag = soup.select_one("#gocuotas-widget .gocuotas-widget-text p")
            if not go_tag:
                return resultados

            texto_go = go_tag.get_text(" ", strip=True)
            m1 = re.search(r"Hasta\s+(\d+)\s+cuotas", texto_go, re.IGNORECASE)
            m2 = re.search(r"de\s+\$([\d\.\,]+)", texto_go)
            banco_match = re.search(r"con\s+Tarjeta de\s+([A-Za-zÁÉÍÓÚÜáéíóúü ]+)", texto_go)

            if m1 and m2:
                num_cuotas = int(m1.group(1))
                precio_texto = m2.group(1).replace(".", "").replace(",", ".")
                try:
                    precio_por_cuota = float(precio_texto)
                except ValueError:
                    precio_por_cuota = None
                banco = banco_match.group(1).strip() if banco_match else ""
                resultados.append({
                    "banco": banco,
                    "num_cuotas": num_cuotas,
                    "precio_por_cuota": precio_por_cuota,
                    "sin_interes": True
                })

            return resultados

        resultados = []
        for idx, item in enumerate(items, start=1):
            url = item.get("link")
            logger.info(f"[{idx}/{len(items)}] Abriendo {url}")
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            total_altura = driver.execute_script("return document.body.scrollHeight")
            altura_actual = 0
            paso = max(int(total_altura / 5), 100)
            while altura_actual < total_altura:
                altura_actual += paso
                driver.execute_script(f"window.scrollTo(0, {altura_actual});")
                time.sleep(0.5)
                total_altura = driver.execute_script("return document.body.scrollHeight")

            time.sleep(1)

            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#gocuotas-widget"))
                )
            except Exception:
                pass

            soup = BeautifulSoup(driver.page_source, "html.parser")

            disp, nodisp = extraer_talles(soup)
            cuotas_bancos = extraer_cuotas_bancos(soup)

            item["disponible"]    = disp
            item["no_disponible"] = nodisp
            item["financiacion"]  = cuotas_bancos

            logger.info(f"  → Modelo (ya extraído): {item.get('modelo_id', 'N/A')}")
            logger.info(f"  → Disponibles: {disp}")
            logger.info(f"  → No disponibles: {nodisp}")
            logger.info(f"  → Cuotas/Bancos: {cuotas_bancos}")
            logger.info("----------------------------------------")

            resultados.append(item)

        driver.quit()

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as out_f:
            json.dump(resultados, out_f, ensure_ascii=False, indent=2)
        logger.info(f"Resultados guardados en {OUTPUT_JSON}")
