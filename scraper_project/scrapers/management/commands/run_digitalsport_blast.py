from django.core.management.base import BaseCommand
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import pandas as pd
import time
from selenium.webdriver.common.by import By
from scrapers.utils_scraping import normalizar_columnas, inferir_categoria

class Command(BaseCommand):
    help = 'Ejecuta el scraper de DigitalSport Blast'

    def add_arguments(self, parser):
        parser.add_argument('--wait', type=int, default=7, help='Tiempo de espera entre scrolls en segundos')

    def handle(self, *args, **options):
        wait_time = options['wait']
        scraper = DigitalSportBlastScraper(wait_time=wait_time)
        try:
            scraper.send_alert("🚀 Iniciando scraping DigitalSport Blast")
            scraper.run()
            scraper.send_alert("✅ Scraper DigitalSport Blast finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper DigitalSport Blast: {str(e)}")
        finally:
            scraper.close_browser()

class DigitalSportBlastScraper(BaseScraper):
    def __init__(self, wait_time=7):
        super().__init__(name="digitalsport_blast")
        self.wait_time = wait_time
        self.secciones = {
            "Calzado": "https://www.digitalsport.com.ar/blast/prods/?category[1]=1",
            "Indumentaria": "https://www.digitalsport.com.ar/blast/prods/?category[1]=2",
            "Accesorios": "https://www.digitalsport.com.ar/blast/prods/?category[1]=13",
        }

    def run(self):
        self.setup_browser()
        for seccion, url_base in self.secciones.items():
            self.logger.info(f"Iniciando sección: {seccion}")
            productos_totales = self.scrapear_seccion(url_base, seccion)
            df = pd.DataFrame(productos_totales)
            df = normalizar_columnas(df)
            filename = f"productos_digitalsport_blast_{self.session_id}_{seccion.lower().replace(' ', '_')}.xlsx"
            self.export_to_excel(df, filename)
            self.send_alert(f"✅ Sección {seccion} finalizada con {len(df)} productos.")
        self.exportar_combinado()
        self.close_browser()

    def scrapear_seccion(self, url_base, seccion):
        productos_totales = []
        pagina = 1

        while True:
            try:
                url = url_base if pagina == 1 else f"{url_base}&page={pagina}"
                self.logger.debug(f"Accediendo a: {url}")
                
                self.driver.get(url)
                time.sleep(self.wait_time)

                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                productos = soup.find_all('div', class_='vtex-search-result-3-x-galleryItem')

                if not productos:
                    if pagina == 1:
                        alerta_msg = f"🚨 *ALERTA CRÍTICA*: No se encontraron productos en la sección {seccion} desde la primera página."
                        self.logger.error(alerta_msg)
                        self.send_alert(alerta_msg)
                    else:
                        self.logger.info("🚫 No se encontraron más productos.")
                    break

                for prod in productos:
                    productos_totales.append(self.parsear_producto(prod, seccion))

                pagina += 1

            except Exception as e:
                error_msg = f"❌ Error accediendo a {url}: {str(e)}"
                self.logger.error(error_msg)
                self.send_alert(error_msg)
                break

        return [p for p in productos_totales if p]


    def scroll_to_bottom_until_no_more(self, max_attempts=5):
        attempts = 0
        last_count = len(self.driver.find_elements(By.CSS_SELECTOR, "a.product"))

        while attempts < max_attempts:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.wait_time)
            current_count = len(self.driver.find_elements(By.CSS_SELECTOR, "a.product"))
            if current_count > last_count:
                attempts = 0
                last_count = current_count
            else:
                attempts += 1

        self.logger.info(f"✅ Scroll finalizado con {last_count} productos detectados.")

    def parsear_producto(self, prod, seccion):
        try:
            nombre = prod.get("data-title", "N/A")
            precio = prod.get("data-price", "N/A")
            marca = prod.get("data-brand", "N/A")
            sku = prod.get("data-sku", "N/A")
            id_producto = prod.get("productid", "N/A")
            link = f"https://www.digitalsport.com.ar{prod.get('href')}"

            imagen_elem = prod.select_one("img.img")
            imagen = f"https://www.digitalsport.com.ar{imagen_elem['data-src']}" if imagen_elem and 'data-src' in imagen_elem.attrs else "N/A"

            cuotas_elem = prod.select_one("div.dues")
            cuotas = cuotas_elem.text.strip() if cuotas_elem else "N/A"

            envio_elem = prod.select_one("div.shipping")
            envio = envio_elem.text.strip() if envio_elem else "N/A"

            tag_elems = prod.select("div.tag_container .tag")
            tags_str = ", ".join([t.text.strip() for t in tag_elems]) if tag_elems else "N/A"

            precio_antes_elem = prod.select_one("div.precio_antes span")
            precio_antes = precio_antes_elem.text.strip() if precio_antes_elem else "N/A"

            descuento_elem = prod.select_one("div.precio_descuento")
            descuento = descuento_elem.text.strip() if descuento_elem else "N/A"

            return {
                "nombre": nombre,
                "marca": marca,
                "precio": precio,
                "precio_anterior": precio_antes,
                "descuento": descuento,
                "cuotas": cuotas,
                "envio_gratis": envio,
                "imagen_url": imagen,
                "link": link,
                "id_producto": id_producto,
                "sku": sku,
                "categoria": seccion,
                "tags": tags_str,
                "hora_inicio": "",
                "hora_fin": "",
                "talles": "N/A",
                "tipo_producto": inferir_categoria(nombre),
                "nombre_pagina": "DigitalSport Blast"
            }
        except Exception as e:
            self.logger.error(f"Error parseando producto: {str(e)}")
            return None
