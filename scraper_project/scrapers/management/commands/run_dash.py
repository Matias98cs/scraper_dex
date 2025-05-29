from django.core.management.base import BaseCommand
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import pandas as pd
import time
from scrapers.utils_scraping import normalizar_columnas, inferir_categoria, inferir_tipo_producto, inferir_variante
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class Command(BaseCommand):
    help = 'Ejecuta el scraper de Dash Deportes'

    def add_arguments(self, parser):
        parser.add_argument('--wait', type=int, default=10, help='Tiempo de espera entre páginas en segundos')

    def handle(self, *args, **options):
        wait_time = options['wait']
        scraper = DashScraper(wait_time=wait_time)
        try:
            scraper.send_alert("🚀 Iniciando scraping Dash")
            scraper.run()
            scraper.send_alert("✅ Scraper Dash finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper Dash: {str(e)}")
        finally:
            scraper.close_browser()

class DashScraper(BaseScraper):
    def __init__(self, wait_time=10):
        super().__init__(name="dash")
        self.wait_time = wait_time
        self.secciones = {
            "Hombre": "https://www.dashdeportes.com.ar/dash-all-products/hombre/unisex?initialMap=productClusterIds&initialQuery=176&map=productclusternames,genero,genero&order=OrderByBestDiscountDESC",
            "Niños": "https://www.dashdeportes.com.ar/bebe/dash-all-products/nino?initialMap=productClusterIds&initialQuery=176&map=genero,productclusternames,genero&order=OrderByBestDiscountDESC",
            "Mujer": "https://www.dashdeportes.com.ar/dash-all-products/mujer/unisex?initialMap=productClusterIds&initialQuery=176&map=productclusternames,genero,genero&order=OrderByBestDiscountDESC"
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

            json_name = f"productos_dash_{self.session_id}_{seccion.lower().replace(' ', '_')}.json"
            self.export_to_json(productos_norm, json_name)
            self.send_alert(f"✅ Sección {seccion} finalizada con {len(productos_norm)} productos.")

            all_items.extend(productos_norm)

        combinado_name = f"productos_dash_{self.session_id}_combinado.json"
        self.exportar_combinado_json(all_items, combinado_name)
        self.send_alert(f"✅ JSON combinado generado con {len(all_items)} productos.")

    def scrapear_seccion(self, url_base, seccion):
        productos_totales = []
        pagina = 1

        while True:
            url = url_base if pagina == 1 else f"{url_base}&page={pagina}"
            self.logger.debug(f"Accediendo a: {url}")
            self.driver.get(url)

            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.vtex-search-result-3-x-galleryItem")
                    )
                )
            except:
                if pagina == 1:
                    alerta = f"🚨 No se cargaron productos en {seccion} en la página inicial."
                    self.logger.error(alerta)
                    self.send_alert(alerta)
                break

            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            productos = soup.select("div.vtex-search-result-3-x-galleryItem")

            if not productos:
                self.logger.info("🚫 No se encontraron más productos.")
                break

            for prod in productos:
                productos_totales.append(self.parsear_producto(prod, seccion))

            pagina += 1

        return [p for p in productos_totales if p]


    # def scrapear_seccion(self, url_base, seccion):
    #     productos_totales = []
    #     pagina = 1

    #     while True:
    #         url = url_base if pagina == 1 else f"{url_base}&page={pagina}"
    #         self.logger.debug(f"Accediendo a: {url}")
    #         self.driver.get(url)
    #         time.sleep(self.wait_time)
    #         soup = BeautifulSoup(self.driver.page_source, "html.parser")
    #         productos = soup.find_all('div', class_='vtex-search-result-3-x-galleryItem')

    #         if not productos:
    #             if pagina == 1:
    #                 alerta_msg = f"🚨 *ALERTA CRÍTICA*: No se encontraron productos en la sección {seccion} desde la primera página."
    #                 self.logger.error(alerta_msg)
    #                 self.send_alert(alerta_msg)
    #             else:
    #                 self.logger.info("🚫 No se encontraron más productos.")
    #             break

    #         for prod in productos:
    #             productos_totales.append(self.parsear_producto(prod, seccion))

    #         pagina += 1

    #     return [p for p in productos_totales if p]

    def parsear_producto(self, producto, seccion):
        try:
            nombre_elem = producto.select_one('span.vtex-product-summary-2-x-productBrand')
            nombre = nombre_elem.text.strip() if nombre_elem else "N/A"

            precio_elem = producto.select_one('span.vtex-store-components-3-x-sellingPriceValue')
            precio = precio_elem.text.strip() if precio_elem else "N/A"

            precio_antes_elem = producto.select_one('span.vtex-store-components-3-x-listPriceValue')
            precio_anterior = precio_antes_elem.text.strip() if precio_antes_elem else "N/A"

            descuento_elem = producto.select_one('div.vtex-store-components-3-x-discountInsideContainer')
            descuento = descuento_elem.text.strip() if descuento_elem else "N/A"

            img_elem = producto.select_one('img.vtex-product-summary-2-x-image')
            imagen_url = img_elem["src"] if img_elem else "N/A"

            link_elem = producto.select_one('a.vtex-product-summary-2-x-clearLink')
            url_relativa = link_elem["href"] if link_elem else ""
            url_completa = f"https://www.dashdeportes.com.ar{url_relativa}" if url_relativa else "Sin link"

            cuotas_elem = producto.select_one('p.dash-theme-6-x-installmentsTxt')
            cuotas = cuotas_elem.text.strip() if cuotas_elem else "N/A"

            envio_elem = producto.select_one('div.dash-theme-6-x-freeShipping')
            envio = envio_elem.text.strip() if envio_elem else "N/A"

            talles = [t.text.strip() for t in producto.select('div.dash-theme-6-x-item')]
            talles_str = ", ".join(talles) if talles else "N/A"

            marca_elem = producto.select_one('img.vtex-product-summary-2-x-productBrandLogo')
            marca = marca_elem["alt"].strip() if marca_elem and "alt" in marca_elem.attrs else "N/A"

            id_producto = url_relativa.split('-')[-1].replace('/p', '') if url_relativa else "N/A"

            return {
                "nombre": nombre,
                "marca": marca,
                "precio": precio,
                "precio_anterior": precio_anterior,
                "descuento": descuento,
                "cuotas": cuotas,
                "envio_gratis": envio,
                "imagen_url": imagen_url,
                "link": url_completa,
                "id_producto": id_producto,
                "sku": "N/A",
                "categoria": seccion,
                "clase_de_producto": inferir_categoria(nombre),
                "tags": "N/A",
                "talles": talles_str,
                "nombre_pagina": "Dash",
                "tipo_de_producto": inferir_tipo_producto(nombre),
                "variante": inferir_variante(nombre),
                "disponible": {},
                "no_disponible": {},
                "modelo_id": "N/A",
            }

        except Exception as e:
            self.logger.error(f"Error parseando producto: {str(e)}")
            return None
