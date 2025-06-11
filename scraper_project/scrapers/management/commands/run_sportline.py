# scrapers/management/commands/import_productos_sportline.py
from django.core.management.base import BaseCommand
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import pandas as pd
import time
from scrapers.utils_scraping import (
    normalizar_columnas,
    inferir_categoria,
    inferir_tipo_producto,
    inferir_variante
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class Command(BaseCommand):
    help = 'Ejecuta el scraper de Sportline'

    def add_arguments(self, parser):
        parser.add_argument('--wait', type=int, default=4,
                            help='Tiempo de espera entre clics en segundos')

    def handle(self, *args, **options):
        wait_time = options['wait']
        scraper = SportlineScraper(wait_time=wait_time)
        try:
            scraper.send_alert("🚀 Iniciando scraping Sportline")
            scraper.run()
            scraper.send_alert("✅ Scraper Sportline finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper Sportline: {str(e)}")
        finally:
            scraper.close_browser()

class SportlineScraper(BaseScraper):
    def __init__(self, wait_time=4):
        super().__init__(name="sportline")
        self.wait_time = wait_time
        self.secciones = {
            "Hombre": "https://www.sportline.com.ar/hombre",
            "Mujer":  "https://www.sportline.com.ar/mujer",
            "Niños":  "https://www.sportline.com.ar/ninos",
            "Deportes": "https://www.sportline.com.ar/deportes",
            "Lanzamientos": "https://www.sportline.com.ar/lanzamientos",
            "Ofertas": "https://www.sportline.com.ar/ofertas"
        }

    def run(self):
        self.setup_browser()
        all_items = []

        for seccion, url in self.secciones.items():
            self.logger.info(f"Iniciando sección {seccion}")
            productos = self.scrapear_seccion(url, seccion)
            all_items.extend(productos)

            df = pd.DataFrame(productos)
            df = normalizar_columnas(df)
            productos_norm = df.to_dict(orient='records')
            json_name = f"productos_sportline_{self.session_id}_{seccion.lower()}.json"
            self.export_to_json(productos_norm, json_name)
            self.send_alert(f"✅ Sección {seccion} finalizada ({len(productos_norm)} items)")

        combinado = f"productos_sportline_{self.session_id}_combinado.json"
        self.exportar_combinado_json(all_items, combinado)
        self.send_alert(f"✅ JSON combinado con {len(all_items)} productos.")

    def scrapear_seccion(self, base_url, seccion):
        productos = []
        pagina = 1
        selector_cards = "div.vtex-search-result-3-x-galleryItem"

        while True:
            url = base_url if pagina == 1 else f"{base_url}?page={pagina}"
            self.logger.info(f"Accediendo a {url}")
            self.driver.get(url)

            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector_cards))
                )
            except:
                if pagina == 1:
                    self.logger.error(f"🚨 No cargaron productos en la página inicial de {seccion}")
                    self.send_alert(f"🚨 No cargaron productos en la página inicial de {seccion}")
                break

            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            cards = soup.select(selector_cards)
            if not cards:
                self.logger.info("✅ No hay más productos, terminando sección.")
                break

            for card in cards:
                item = self.parsear_producto(card, seccion)
                if item:
                    productos.append(item)

            self.logger.info(f"Página {pagina} de {seccion}: {len(cards)} productos")
            pagina += 1
            time.sleep(self.wait_time)

        return productos


    def parsear_producto(self, producto, seccion):
        try:
            nombre = producto.select_one("h3.vtex-product-summary-2-x-productNameContainer")
            nombre = nombre.text.strip() if nombre else "N/A"

            marca = producto.select_one("span.vtex-store-components-3-x-productBrandName")
            marca = marca.text.strip() if marca else "N/A"

            precio = producto.select_one("span.vtex-product-price-1-x-sellingPriceValue")
            precio = precio.text.strip() if precio else "N/A"

            precio_ant = producto.select_one("span.vtex-product-price-1-x-listPriceValue")
            precio_anterior = precio_ant.text.strip() if precio_ant else "N/A"

            descuento_elem = producto.select_one('span.vtex-product-price-1-x-savingsPercentage')
            if descuento_elem:
                descuento = descuento_elem.text.strip()
            else:
                descuento_elem = producto.select_one('div.vtex-store-components-3-x-discountInsideContainer')
                descuento = descuento_elem.text.strip() if descuento_elem else "N/A"

            img = producto.select_one("img.sportline-custom-product-summary-image-0-x-mainImageHovered")
            imagen_url = img["src"] if img else "N/A"

            link_tag = producto.select_one("a.vtex-product-summary-2-x-clearLink")
            href = link_tag["href"] if link_tag else ""
            sku = href.split("-")[-1].replace("/p", "") if href else "N/A"
            link = f"https://www.sportline.com.ar{href}" if href else "N/A"

            cuotas = producto.select_one("span.vtex-product-price-1-x-installmentsNumber")
            cuotas = cuotas.text.strip() if cuotas else "N/A"

            envio_gratis = "Si" if producto.select_one(
                "div.cruce-admin-free-shipping-2-x-highlightContainer"
            ) else "No"


            return {
                "nombre": nombre,
                "marca": marca,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "descuento": descuento,
                "cuotas": f"{cuotas} cuotas sin interés" if cuotas != "N/A" else "N/A",
                "envio_gratis": envio_gratis,
                "imagen_url": imagen_url,
                "link": link,
                "id_producto": sku,
                "sku": sku,
                "categoria": seccion,
                "clase_de_producto": inferir_categoria(nombre),
                "tags": "N/A",
                "talles": "N/A",
                "nombre_pagina": "Sportline",
                "tipo_de_producto": inferir_tipo_producto(nombre),
                "variante": inferir_variante(nombre),
                "disponible": {},
                "no_disponible": {},
                "modelo_id": sku,
            }
        except Exception as e:
            self.logger.error(f"Error parseando producto: {e}")
            return None
