import json
import re
import logging
import time
import threading
import resource
from queue import Queue, Empty
from pathlib import Path
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, JavascriptException, WebDriverException
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
import threading, time


from scrapers.utils import (
    setup_logger,
    send_alert_message,
    initialize_driver_remote,
    initialize_driver_local,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(settings.BASE_DIR)
JSON_DIR = BASE_DIR / "json_pruebas"

JSON_PATH = JSON_DIR / "productos_dash_20250530_124755_combinado.json"
PROGRESS_INTERVAL = 30

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
    except (TimeoutException, JavascriptException, WebDriverException) as e:
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

def worker(task_queue, driver_queue, resultados, lock, total, use_local):
    tname = threading.current_thread().name

    while True:
        try:
            idx, item = task_queue.get_nowait()
        except Empty:
            return

        mem_inicial = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.info(f"[{tname}] Inicio item {idx}/{total} - Memoria inicial (KB): {mem_inicial}")

        driver = None
        try:
            driver = driver_queue.get()
            url = item.get("link", "")
            logger.info(f"[{tname}] [{idx}/{total}] Abriendo {url}")

            # Intentamos navegar. Si falla al primer driver.get, capturamos aquí:
            try:
                driver.get(url)
            except WebDriverException as e:
                logger.error(f"[{tname}] [{idx}/{total}] Driver inválido (GET): {e}")

                # Cerramos el driver “muerto” si existe
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

                # Ahora intentamos re‐crear el driver, PERO con timeout interno
                def crear_driver():
                    return initialize_driver_local() if use_local else initialize_driver_remote()

                nuevo = None
                # Usamos ThreadPoolExecutor sólo para imponer timeout al crear el driver
                with ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(crear_driver)
                    try:
                        # Esperamos hasta 10 segundos por el initialize_driver
                        nuevo = future.result(timeout=10)
                    except Exception as ex_init:
                        logger.error(f"[{tname}] [{idx}/{total}] No pude reinicializar el driver: {ex_init}")
                        # Si falla o hace timeout, cancelamos la tarea
                        future.cancel()
                        nuevo = None

                # Si pudimos instanciar un nuevo driver, lo ponemos en el pool; si no, 
                # no podremos seguir con Selenium, pero al menos avanzamos:
                if nuevo:
                    driver_queue.put(nuevo)
                    driver = nuevo
                    try:
                        driver.get(url)
                    except WebDriverException as e2:
                        logger.error(f"[{tname}] [{idx}/{total}] Segundo intento de GET falló: {e2}")
                        # De nuevo, no insisto más: dejo driver “colgado” para que se cierre en finally
                else:
                    # Ya no tengo driver válido: dejo driver = None y sigo adelante
                    driver = None

            # Si llegamos hasta aquí (con o sin driver activo), seguimos intentando extraer
            if driver:
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except (TimeoutException, WebDriverException):
                    logger.warning(f"[{tname}] [{idx}/{total}] Timeout esperando readyState")

                scroll_page(driver)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.dash-theme-6-x-wrapperModalCC"))
                    )
                except (TimeoutException, WebDriverException):
                    logger.warning(f"[{tname}] [{idx}/{total}] Widget cuotas no apareció en 10s")

                time.sleep(1)
                soup = BeautifulSoup(driver.page_source, "html.parser")

                try:
                    modelo = extraer_modelo_id(soup)
                    disp, nodisp = extraer_talles(soup)
                    cuotas_bancos = extraer_cuotas_bancos(soup)
                except Exception as e:
                    logger.warning(f"[{tname}] [{idx}/{total}] Error extrayendo datos: {e}")
                    modelo, disp, nodisp, cuotas_bancos = "N/A", [], [], []

                num_wrappers = len(soup.select("div.dash-theme-6-x-wrapperModalCC"))
                logger.info(f"[{tname}] [{idx}/{total}] Encontré {num_wrappers} wrappers en {url}")

                item["modelo_id"]     = modelo
                item["disponible"]    = disp
                item["no_disponible"] = nodisp
                item["financiacion"]  = cuotas_bancos

                logger.info(f"[{tname}] [{idx}/{total}] → Modelo: {modelo}")
                logger.info(f"[{tname}] [{idx}/{total}] → Disponibles: {disp}")
                logger.info(f"[{tname}] [{idx}/{total}] → No disponibles: {nodisp}")
                logger.info(f"[{tname}] [{idx}/{total}] → Cuotas/Bancos: {cuotas_bancos}")

                mem_final = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                logger.info(f"[{tname}] Item {idx} finalizado - Memoria final (KB): {mem_final}")

        except WebDriverException as e:
            # Cualquier otro WebDriverException que surgiera fuera del primer get()—
            # no quiero que cuelgue el hilo.  
            logger.error(f"[{tname}] [{idx}/{total}] WebDriverException imprevisto: {e}")
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            driver = None
            # Reintento de inicializar, con el mismo patrón de timeout
            def crear_driver():
                return initialize_driver_local() if use_local else initialize_driver_remote()

            nuevo = None
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(crear_driver)
                try:
                    nuevo = future.result(timeout=10)
                except Exception as ex_init:
                    logger.error(f"[{tname}] [{idx}/{total}] Error reinicializando driver: {ex_init}")
                    future.cancel()
                    nuevo = None

            if nuevo:
                driver_queue.put(nuevo)
            # Luego sigo de todas formas para anexar item con defaults:
            item["modelo_id"]     = item.get("modelo_id", "N/A")
            item["disponible"]    = item.get("disponible", [])
            item["no_disponible"] = item.get("no_disponible", [])
            item["financiacion"]  = item.get("financiacion", [])

        except Exception as e:
            logger.error(f"[{tname}] [{idx}/{total}] Error inesperado: {e}")
            # Asigno defaults y continúo:
            item["modelo_id"]     = item.get("modelo_id", "N/A")
            item["disponible"]    = item.get("disponible", [])
            item["no_disponible"] = item.get("no_disponible", [])
            item["financiacion"]  = item.get("financiacion", [])

        finally:
            if driver:
                try:
                    driver_queue.put(driver)
                except Exception as e_put:
                    logger.warning(f"[{tname}] Error devolviendo driver al pool: {e_put}")

            with lock:
                resultados.append(item)

            task_queue.task_done()
            logger.info(f"[{tname}] Terminado item {idx}/{total}")

def progress_reporter(total, resultados, stop_event):
    while not stop_event.is_set():
        procesados = len(resultados)
        porcentaje = (procesados / total) * 100 if total else 100
        logger.info(f"Progreso: {procesados}/{total} ({porcentaje:.2f}%)")
        stop_event.wait(PROGRESS_INTERVAL)

class Command(BaseCommand):
    help = 'Scraper Dash con pool de WebDrivers, threading variable, progreso y alertas a Slack'

    def add_arguments(self, parser):
        parser.add_argument(
            '--local',
            action='store_true',
            help='Usar ChromeDriver local en lugar de remoto'
        )
        parser.add_argument(
            '--threads',
            type=int,
            default=4,
            help='Cantidad de hilos a utilizar (por defecto: 4)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Nombre de archivo JSON de salida (sin path). Si no se proporciona, se crea uno con formato dash-DD-MM-YYYY-HHMM.json'
        )

    def handle(self, *args, **options):
        use_local = options['local']
        num_threads = options['threads']
        output_name = options.get('output')

        if output_name:
            if not output_name.lower().endswith(".json"):
                output_name = f"{output_name}.json"
        else:
            ahora = datetime.now()
            fecha_hora = ahora.strftime("%d-%m-%Y-%H%M%S")
            output_name = f"dash-{fecha_hora}.json"

        OUTPUT_PATH = JSON_DIR / output_name

        send_alert_message(f"🚀 Scraper Dash iniciado con {num_threads} hilos. Salida: {output_name}")

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S"
        )

        inicio_dt = datetime.now()
        inicio_str = inicio_dt.strftime("%d-%m-%Y %H:%M:%S")
        start_time = time.time()

        logger.info(f"Fecha/hora de inicio: {inicio_str}")

        try:
            with open(JSON_PATH, encoding="utf-8") as f:
                items = json.load(f)
            total = len(items)
            logger.info(f"Hilos activos al inicio: {threading.active_count()}")
            logger.info(f"Cargados {total} productos desde {JSON_PATH}")

            driver_queue = Queue(maxsize=num_threads)
            for _ in range(num_threads):
                try:
                    if use_local:
                        driver_queue.put(initialize_driver_local())
                    else:
                        driver_queue.put(initialize_driver_remote())
                except Exception as e:
                    logger.error(f"Error iniciando driver {'local' if use_local else 'remoto'}: {e}")

            task_queue = Queue()
            for idx, item in enumerate(items, start=1):
                task_queue.put((idx, item))

            resultados = []
            lock = threading.Lock()

            stop_event = threading.Event()
            reporter = threading.Thread(
                target=progress_reporter,
                args=(total, resultados, stop_event),
                name="ProgressReporter",
                daemon=True
            )
            reporter.start()

            threads = []
            for i in range(num_threads):
                t = threading.Thread(
                    target=worker,
                    name=f"ScraperDash_{i+1}",
                    args=(task_queue, driver_queue, resultados, lock, total, use_local)
                )
                threads.append(t)
                t.start()

            task_queue.join()

            stop_event.set()
            reporter.join(timeout=5)

            while not driver_queue.empty():
                try:
                    d = driver_queue.get_nowait()
                    d.quit()
                except Empty:
                    break
                except Exception:
                    pass

            with open(OUTPUT_PATH, 'w', encoding='utf-8') as out_f:
                json.dump(resultados, out_f, ensure_ascii=False, indent=2)

            fin_dt = datetime.now()
            fin_str = fin_dt.strftime("%d-%m-%Y %H:%M:%S")
            end_time = time.time()
            duration = end_time - start_time
            duration_str = time.strftime("%H:%M:%S", time.gmtime(duration))

            logger.info(f"Fecha/hora de finalización: {fin_str}")
            logger.info(f"Duración total: {duration_str}")
            logger.info(f"Resultados guardados en {OUTPUT_PATH}")
            logger.info(f"Hilos activos al final: {threading.active_count()}")

            send_alert_message(
                f"✅ Scraper completado: {len(resultados)}/{total} productos procesados.\n"
                f"Archivo: {output_name}\n"
                f"Inicio: {inicio_str}\n"
                f"Fin: {fin_str}\n"
                f"Duración: {duration_str}"
            )

        except Exception as e:
            logger.error(f"Fallo general del scraper: {e}")
            send_alert_message(f"❌ Scraper producto por producto falló con error: {e}\nInicio: {inicio_str}")
            raise