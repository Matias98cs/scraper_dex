from django.core.management.base import BaseCommand
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import pandas as pd
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from scrapers.utils_scraping import (
    normalizar_columnas,
    inferir_categoria,
    inferir_tipo_producto,
    inferir_variante,
)

class Command(BaseCommand):
    help = 'Ejecuta el scraper de Dexter'

    def add_arguments(self, parser):
        parser.add_argument(
            '--wait', type=int, default=5,
            help='Tiempo de espera tras cada carga'
        )

    def handle(self, *args, **options):
        wait_time = options['wait']
        scraper = DexterScraper(wait_time=wait_time)
        try:
            scraper.send_alert("🚀 Iniciando scraping Dexter")
            scraper.run()
            scraper.send_alert("✅ Scraper Dexter finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper Dexter: {str(e)}")
        finally:
            scraper.close_browser()


class DexterScraper(BaseScraper):
    def __init__(self, wait_time=5):
        super().__init__(name="dexter")
        self.wait_time = wait_time
        self.secciones = {
            "Hombre":      "https://www.dexter.com.ar/hombre",
            "Mujer":       "https://www.dexter.com.ar/mujer",
            "Niños":       "https://www.dexter.com.ar/categorias/infantil",
            "Zapatillas":  "https://www.dexter.com.ar/zapatillas",
            "Lanzamiento": "https://www.dexter.com.ar/categorias?prefn1=isLaunch&prefv1=true",
            "Sale":        "https://www.dexter.com.ar/sale",
        }

    def run(self):
        self.setup_browser()
        all_items = []

        for seccion, url in self.secciones.items():
            self.logger.info(f"Iniciando sección: {seccion}")
            productos = self.scrapear_seccion(url, seccion)

            df = pd.DataFrame(productos)
            df = normalizar_columnas(df)
            items = df.to_dict(orient='records')

            json_name = f"productos_dexter_{self.session_id}_{seccion.lower()}.json"
            self.export_to_json(items, json_name)
            self.send_alert(f"✅ Sección {seccion} finalizada con {len(items)} productos.")

            all_items.extend(items)

        combinado_name = f"productos_dexter_{self.session_id}_combinado.json"
        self.exportar_combinado_json(all_items, combinado_name)
        self.send_alert(f"✅ JSON combinado generado con {len(all_items)} productos.")
        self.close_browser()

    def scrapear_seccion(self, url, seccion):
        self.driver.get(url)
        self._close_postal_modal()
        self._cargar_todos()

        elementos = self.driver.find_elements(By.CSS_SELECTOR, "div.product")
        if not elementos:
            alerta = f"🚨 *ALERTA CRÍTICA*: No se encontraron productos en {seccion}."
            self.logger.error(alerta)
            self.send_alert(alerta)
            return []

        self.logger.info(f"📦 Total de productos encontrados: {len(elementos)}")
        lista = []
        for elem in elementos:
            html = elem.get_attribute("outerHTML")
            soup = BeautifulSoup(html, "html.parser")
            prod = self.parsear_producto(soup, seccion)
            if prod:
                lista.append(prod)

        # eliminar duplicados por id_producto
        uniques = {p["id_producto"]: p for p in lista if p["id_producto"] != "N/A"}
        return list(uniques.values())

    def _close_postal_modal(self):
        """
        Cierra el modal de Código Postal si aparece, haciendo clic en su botón de cierre
        y eliminando cualquier overlay que quede.
        """
        try:
            close_btn = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "img.close-img"))
            )
            close_btn.click()
            self.driver.execute_script("""
                document.querySelectorAll('.modal-backdrop, .modal-overlay').forEach(e => e.remove());
            """)
            self.logger.info("🛠️ Modal postal cerrado y overlay removido.")
        except TimeoutException:
            pass


    def _cargar_todos(self, max_attempts=50):
        """
        Hace scroll y clicks en 'Quiero ver más', ocultando headers fijos para que no
        interfieran con el click.
        """
        attempts = 0
        while attempts < max_attempts:
            # Oculta todos los headers que pudieran tapar el botón
            self.driver.execute_script("""
                document.querySelectorAll('header, .fixed').forEach(h => h.style.display = 'none');
            """)

            # Lleva el contenedor del botón al centro de la vista
            try:
                sentinel = WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.show-more"))
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", sentinel
                )
            except TimeoutException:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            time.sleep(self.wait_time)

            # Busca y hace click en el botón “Quiero ver más”
            try:
                btn = WebDriverWait(self.driver, self.wait_time).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.more"))
                )
            except (NoSuchElementException, TimeoutException):
                self.logger.info("✅ No hay más productos para cargar.")
                break

            btn.click()
            self.logger.info("🔄 Click en 'Quiero ver más'")
            time.sleep(self.wait_time)
            attempts += 1

        if attempts >= max_attempts:
            self.logger.warning("⚠️ Se alcanzó el máximo de intentos de 'Quiero ver más'")


    def parsear_producto(self, soup, seccion):
        try:
            cont = soup.select_one("div.product")
            pid  = cont.get("data-pid", "N/A") if cont else "N/A"

            title_el = soup.select_one("div.pdp-link a.link")
            nombre = title_el.text.strip() if title_el else "N/A"
            href   = title_el["href"] if title_el and title_el.has_attr("href") else ""
            link   = f"https://www.dexter.com.ar{href}" if href else "N/A"

            price_el = soup.select_one("span.sales .value")
            precio   = price_el.text.strip() if price_el else "N/A"

            # precio anterior
            prev_el = soup.select_one("span.sales del span.value")
            if prev_el:
                if prev_el.has_attr("content"):
                    precio_anterior = prev_el["content"]
                else:
                    precio_anterior = prev_el.text.strip()
            else:
                precio_anterior = "N/A"

            # descuento (opcional, si quieres)
            discount_el = soup.select_one("fieldset legend")
            descuento = discount_el.text.strip() if discount_el else "N/A"

            # cuotas
            cuotas_el = soup.select_one("div.installments-container span")
            cuotas = cuotas_el.text.strip() if cuotas_el else "N/A"

            img_el = soup.select_one("img.tile-image.primary-image")
            imagen  = img_el["src"] if img_el and img_el.has_attr("src") else "N/A"

            return {
                "nombre": nombre,
                "marca": "N/A",
                "precio": precio,
                "precio_anterior": precio_anterior,
                "descuento": descuento,
                "cuotas": cuotas,
                "envio_gratis": "N/A",
                "imagen_url": imagen,
                "link": link,
                "id_producto": pid,
                "sku": pid,
                "categoria": seccion,
                "clase_de_producto": inferir_categoria(nombre),
                "tags": "N/A",
                "talles": "N/A",
                "nombre_pagina": "Dexter",
                "tipo_de_producto": inferir_tipo_producto(nombre),
                "variante": inferir_variante(nombre),
                "disponible": {},
                "no_disponible": {},
                "modelo_id": pid,
            }

        except Exception as e:
            self.logger.error(f"Error parseando producto: {e}")
            return None
