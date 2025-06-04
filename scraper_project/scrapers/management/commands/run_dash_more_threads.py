import json
import re
import logging
import time
import threading
import resource
from queue import Queue, Empty
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, JavascriptException
from pathlib import Path
from django.conf import settings
from selenium.webdriver.chrome.service import Service as ChromeService
import shutil
import os

logger = logging.getLogger(__name__)

BASE_DIR = Path(settings.BASE_DIR)

# JSON_PATH   = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_20250530_124755_combinado.json"
# OUTPUT_JSON = "/Users/matiascampos/Anocuta/scraper_project/scraper_project/outputs/dash/productos_dash_more_threads_2.json"

JSON_DIR = BASE_DIR / "json_pruebas"

JSON_PATH   = JSON_DIR / "productos_dash_20250530_124755_combinado.json"
OUTPUT_JSON = JSON_DIR / "dash_more_threads_1.json"

MAX_THREADS = 4

def scroll_page(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        scroll_height = driver.execute_script("return document.body.scrollHeight")
        if not scroll_height:
            logger.warning("No se obtuvo scrollHeight; saltando scroll.")
            return

        for pct in range(0, 101, 15):
            pos = (pct / 100) * scroll_height
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(0.2)
    except (TimeoutException, JavascriptException) as e:
        logger.warning(f"Error al desplazar la página: {e}")


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


def initialize_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.set_capability('browserless:token', os.environ['BROWSER_TOKEN'])
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Remote(
        command_executor=os.environ['BROWSER_WEBDRIVER_ENDPOINT'],
        options=chrome_options
    )
    driver.implicitly_wait(1)
    return driver



def worker(task_queue, driver_queue, resultados, lock, headless, total):
    tname = threading.current_thread().name

    while True:
        try:
            idx, item = task_queue.get_nowait()
        except Empty:
            return

        mem_inicial = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.info(f"[{tname}] Uso de memoria al iniciar tarea para item {idx}/{total} (KB): {mem_inicial}")

        try:
            driver = driver_queue.get()
            url = item.get("link")
            logger.info(f"[{tname}] [{idx}/{total}] Abriendo {url}")
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except TimeoutException:
                logger.warning(f"[{tname}] [{idx}/{total}] document.readyState no llegó a 'complete' en 10s")

            scroll_page(driver)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.dash-theme-6-x-wrapperModalCC"))
                )
            except TimeoutException:
                logger.warning(f"[{tname}] [{idx}/{total}] El widget de cuotas no apareció en 10s")

            time.sleep(1)
            soup = BeautifulSoup(driver.page_source, "html.parser")

            modelo, disp, nodisp, cuotas_bancos = "N/A", [], [], []
            try:
                modelo       = extraer_modelo_id(soup)
                disp, nodisp = extraer_talles(soup)
                cuotas_bancos = extraer_cuotas_bancos(soup)
            except Exception as e:
                logger.warning(f"[{tname}] [{idx}/{total}] Error al extraer talles/cuotas: {e}")

            num_wrappers = len(soup.select("div.dash-theme-6-x-wrapperModalCC"))
            logger.info(f"[{tname}] [{idx}/{total}] Encontré {num_wrappers} wrappers de cuotas en {url}")

            item["modelo_id"]      = modelo
            item["disponible"]     = disp
            item["no_disponible"]  = nodisp
            item["financiacion"]   = cuotas_bancos

            logger.info(f"[{tname}] [{idx}/{total}]   → Modelo: {modelo}")
            logger.info(f"[{tname}] [{idx}/{total}]   → Disponibles: {disp}")
            logger.info(f"[{tname}] [{idx}/{total}]   → No disponibles: {nodisp}")
            logger.info(f"[{tname}] [{idx}/{total}]   → Cuotas/Bancos: {cuotas_bancos}")
            logger.info(f"[{tname}] ----------------------------------------")

            mem_final = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            logger.info(f"[{tname}] Uso de memoria al finalizar item {idx} (KB): {mem_final}")

        except Exception as e:
            logger.error(f"[{tname}] [{idx}/{total}] Error procesando {url}: {e}")
            item["modelo_id"]      = item.get("modelo_id", "N/A")
            item["disponible"]     = []
            item["no_disponible"]  = []
            item["financiacion"]   = []
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            new_driver = initialize_driver(headless)
            driver_queue.put(new_driver)
            with lock:
                resultados.append(item)
            task_queue.task_done()

        logger.info(f"[{tname}] Terminado procesamiento de item {idx}/{total}")


class Command(BaseCommand):
    help = 'Scraper Dash con pool de WebDrivers y threading manual'

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
        logger.info(f"Hilos activos al inicio: {threading.active_count()}")
        logger.info(f"Cargados {total} productos desde {JSON_PATH}")

        driver_queue = Queue(maxsize=MAX_THREADS)
        for _ in range(MAX_THREADS):
            driver_queue.put(initialize_driver(headless))

        task_queue = Queue()
        for idx, item in enumerate(items, start=1):
            task_queue.put((idx, item))

        resultados = []
        lock = threading.Lock()

        threads = []
        for i in range(MAX_THREADS):
            t = threading.Thread(
                target=worker,
                name=f"ScraperDash_{i}",
                args=(task_queue, driver_queue, resultados, lock, headless, total)
            )
            threads.append(t)
            t.start()

        task_queue.join()

        while not driver_queue.empty():
            try:
                d = driver_queue.get_nowait()
                d.quit()
            except Empty:
                break

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as out_f:
            json.dump(resultados, out_f, ensure_ascii=False, indent=2)

        logger.info(f"Resultados guardados en {OUTPUT_JSON}")
        logger.info(f"Hilos activos al final: {threading.active_count()}")
