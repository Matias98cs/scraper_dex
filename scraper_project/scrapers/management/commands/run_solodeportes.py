from django.core.management.base import BaseCommand
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import pandas as pd
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapers.utils_scraping import (
    normalizar_columnas,
    inferir_categoria,
    inferir_tipo_producto,
    inferir_variante,
)
from selenium.common.exceptions import TimeoutException

class Command(BaseCommand):
    help = 'Ejecuta el scraper de Solo Deportes'

    def add_arguments(self, parser):
        parser.add_argument('--wait', type=int, default=5, help='Timeout máximo de espera en segundos')

    def handle(self, *args, **options):
        timeout = options['wait']
        scraper = SoloDeportesScraper(wait_time=timeout)
        try:
            scraper.send_alert("🚀 Iniciando scraping Solo Deportes")
            scraper.run()
            scraper.send_alert("✅ Scraper Solo Deportes finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper Solo Deportes: {str(e)}")
        finally:
            scraper.close_browser()


class SoloDeportesScraper(BaseScraper):
    def __init__(self, wait_time=5):
        super().__init__(name="solodeportes")
        self.wait_time = wait_time
        self.secciones = {
            "Hombre":    "https://www.solodeportes.com.ar/hombre.html?product_list_order=mst_f2",
            "Mujer":     "https://www.solodeportes.com.ar/dama.html?product_list_order=mst_f2",
            "Niños":     "https://www.solodeportes.com.ar/ni-os-sd.html?product_list_order=mst_f2",
            "Accesorios":"https://www.solodeportes.com.ar/accesorios.html",
            "Deportes":  "https://www.solodeportes.com.ar/deportes.html",
            "Escolares": "https://www.solodeportes.com.ar/escolares.html",
        }

    def run(self):
        self.setup_browser()
        all_items = []

        for seccion, url_base in self.secciones.items():
            self.logger.info(f"Iniciando sección: {seccion}")
            productos = self.scrapear_seccion(url_base, seccion)

            df = pd.DataFrame(productos)
            df = normalizar_columnas(df)
            productos_norm = df.to_dict(orient='records')

            json_name = f"productos_solodeportes_{self.session_id}_{seccion.lower()}.json"
            self.export_to_json(productos_norm, json_name)
            self.send_alert(f"✅ Sección {seccion} finalizada con {len(productos_norm)} productos.")

            all_items.extend(productos_norm)

        combinado_name = f"productos_solodeportes_{self.session_id}_combinado.json"
        self.exportar_combinado_json(all_items, combinado_name)
        self.send_alert(f"✅ JSON combinado generado con {len(all_items)} productos.")

        self.close_browser()

    def scrapear_seccion(self, url, seccion):
        self.driver.get(url)
        WebDriverWait(self.driver, self.wait_time).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.item.product.product-item"))
        )

        productos_totales = []
        seen = set()
        prev_count = 0

        # Intentamos scroll en window
        while True:
            # scrolleamos al sentinel
            try:
                sentinel = WebDriverWait(self.driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer > div.page-content > ul.footer-cols"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(false);", sentinel)
            except TimeoutException:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            time.sleep(self.wait_time)

            current_count = len(self.driver.find_elements(By.CSS_SELECTOR, "li.item.product.product-item"))
            if current_count == prev_count:
                break
            prev_count = current_count

        # parsear únicos
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        for prod in soup.select("li.item.product.product-item"):
            parsed = self.parsear_producto(prod, seccion)
            key = parsed.get("sku") or parsed.get("link")
            if parsed and key not in seen:
                seen.add(key)
                productos_totales.append(parsed)

        return productos_totales
    def parsear_producto(self, producto, seccion):
        try:
            nombre_elem = producto.select_one("p.product-item-name")
            nombre = nombre_elem.text.strip() if nombre_elem else "N/A"

            sku_elem = producto.select_one("p.product-item-sku span.value")
            sku = sku_elem.text.strip() if sku_elem else "N/A"

            link_elem = producto.find("a", href=True, onclick=True)
            link = link_elem["href"] if link_elem else "N/A"

            img = producto.select_one("span.product-image-container img.product-image-photo")
            imagen_url = img["src"] if img else "N/A"

            brand = producto.select_one("div.brand-container img.brand")
            marca = brand.get("alt", "N/A").strip() if brand else "N/A"

            precio_elem = producto.select_one("div.price-box span.price")
            precio = precio_elem.text.strip() if precio_elem else "N/A"
            sin_imp_elem = producto.select_one("span.tax-display div:nth-child(2)")
            precio_anterior = sin_imp_elem.text.strip() if sin_imp_elem else "N/A"

            return {
                "nombre": nombre,
                "marca": marca,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "descuento": "N/A",
                "cuotas": "N/A",
                "envio_gratis": False,
                "imagen_url": imagen_url,
                "link": link,
                "id_producto": sku,
                "sku": sku,
                "categoria": seccion,
                "clase_de_producto": inferir_categoria(nombre),
                "tags": "N/A",
                "talles": "N/A",
                "nombre_pagina": "SoloDeportes",
                "tipo_de_producto": inferir_tipo_producto(nombre),
                "variante": inferir_variante(nombre),
                "disponible": {},
                "no_disponible": {},
                "modelo_id": sku,
            }

        except Exception as e:
            self.logger.error(f"Error parseando producto: {e}")
            return None
