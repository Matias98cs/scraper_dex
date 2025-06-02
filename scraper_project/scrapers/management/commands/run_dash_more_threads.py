import json
import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import threading

logger = logging.getLogger(__name__)

JSON_PATH   = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_20250530_124755_combinado.json"
OUTPUT_JSON = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_20250530_124755_more_threads.json"
MAX_THREADS = 4

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

def extraer_cuotas_bancos(soup):
    resultados = []
    for wrapper in soup.select("div.dash-theme-6-x-wrapperModalCC"):
        banco = ""
        banco_el = wrapper.select_one("div.dash-theme-6-x-topBarTarjetasCC p")
        if banco_el:
            banco = banco_el.get_text(strip=True)

        texto_cuota = ""
        cuota_el = wrapper.select_one("div.dash-theme-6-x-containerCuotasCC p")
        if cuota_el:
            texto_cuota = cuota_el.get_text(strip=True)

        num_cuotas       = None
        precio_por_cuota = None
        sin_interes      = None

        m1 = re.search(r"(\d+)\s+cuotas?", texto_cuota, re.IGNORECASE)
        if m1:
            num_cuotas = int(m1.group(1))

        if re.search(r"sin\s+interés", texto_cuota, re.IGNORECASE):
            sin_interes = True
        elif re.search(r"con\s+interés", texto_cuota, re.IGNORECASE):
            sin_interes = False

        m2 = re.search(r"\$\s*([\d\.\,]+)", texto_cuota)
        if m2:
            precio_texto = m2.group(1)
            precio_texto_norm = precio_texto.replace(".", "").replace(",", ".")
            try:
                precio_por_cuota = float(precio_texto_norm)
            except ValueError:
                precio_por_cuota = None

        if num_cuotas is not None or precio_por_cuota is not None or sin_interes is not None:
            resultados.append({
                "banco":            banco,
                "num_cuotas":       num_cuotas,
                "precio_por_cuota": precio_por_cuota,
                "sin_interes":      sin_interes,
            })

    return resultados

def procesar_item(item, headless, idx, total, wait_time=10):
    chrome_opts = Options()
    if headless:
        chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=chrome_opts)
    driver.implicitly_wait(1)

    url = item.get("link")
    try:
        logger.info(f"[{idx}/{total}] Abriendo {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except:
            pass

        total_altura = driver.execute_script("return document.body.scrollHeight")
        altura_actual = 0
        paso = max(int(total_altura / 5), 500)
        while altura_actual < total_altura:
            altura_actual += paso
            driver.execute_script(f"window.scrollTo(0, {altura_actual});")
            time.sleep(0.5)
            total_altura = driver.execute_script("return document.body.scrollHeight")

        time.sleep(1)

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.dash-theme-6-x-wrapperModalCC"))
            )
        except:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")

        modelo, disp, nodisp, cuotas_bancos = "N/A", [], [], []
        try:
            modelo       = extraer_modelo_id(soup)
            disp, nodisp = extraer_talles(soup)
            cuotas_bancos = extraer_cuotas_bancos(soup)
        except Exception as e:
            logger.warning(f"[{idx}/{total}] Error al extraer datos de talles/cuotas para {url}: {e}")

        item["modelo_id"]      = modelo
        item["disponible"]     = disp
        item["no_disponible"]  = nodisp
        item["financiacion"]   = cuotas_bancos

        logger.info(f"[{idx}/{total}]   → Modelo: {modelo}")
        logger.info(f"[{idx}/{total}]   → Disponibles: {disp}")
        logger.info(f"[{idx}/{total}]   → No disponibles: {nodisp}")
        logger.info(f"[{idx}/{total}]   → Cuotas/Bancos: {cuotas_bancos}")
        logger.info("----------------------------------------")

    except Exception as e:
        logger.error(f"[{idx}/{total}] Error procesando {url}: {e}")
    finally:
        driver.quit()

    return item

class Command(BaseCommand):
    help = 'Scraper Dash (paralelizado con ThreadPoolExecutor)'

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
            format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S"
        )

        with open(JSON_PATH, encoding="utf-8") as f:
            items = json.load(f)
        total = len(items)
        logger.info(f"Cargados {total} productos desde {JSON_PATH}")
        logger.info(f"Threads activos al inicio: {threading.active_count()}")

        resultados = []
        futures = []

        with ThreadPoolExecutor(max_workers=MAX_THREADS, thread_name_prefix="ScraperDash") as executor:
            for idx, item in enumerate(items, start=1):
                futures.append(
                    executor.submit(procesar_item, item, headless, idx, total)
                )

            for fut in as_completed(futures):
                resultados.append(fut.result())
                logger.info(f"Hilos activos ahora: {threading.active_count()}")

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as out_f:
            json.dump(resultados, out_f, ensure_ascii=False, indent=2)
        logger.info(f"Resultados guardados en {OUTPUT_JSON}")
        logger.info(f"Threads activos al final: {threading.active_count()}")
