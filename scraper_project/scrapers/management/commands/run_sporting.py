# scrapers/management/commands/run_sportingio.py

import time
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from django.core.management.base import BaseCommand
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from scrapers.base_scraper import BaseScraper
from scrapers.utils_scraping import normalizar_columnas, inferir_categoria, columnas_base

class Command(BaseCommand):
    help = 'Ejecuta el scraper de SportingIO'

    def add_arguments(self, parser):
        parser.add_argument('--wait', type=int, default=5,
                            help='Tiempo de espera entre requests y scrolls')

    def handle(self, *args, **options):
        wait_time = options['wait']
        scraper = SportingIOScraper(wait_time=wait_time)
        try:
            scraper.send_alert("🚀 Iniciando scraping SportingIO")
            scraper.run()
            scraper.send_alert("✅ Scraper SportingIO finalizado correctamente")
        except Exception as e:
            scraper.logger.error(str(e))
            scraper.send_alert(f"❌ Error en scraper SportingIO: {str(e)}")
        finally:
            scraper.close_browser()


class SportingIOScraper(BaseScraper):
    def __init__(self, wait_time=5):
        super().__init__(name="sportingio")
        self.wait_time = wait_time
        self.secciones = {
            "Hombre": "https://www.sporting.com.ar/hombre"
        }

    def run(self):
        self.setup_browser()
        for seccion, url in self.secciones.items():
            self.logger.info(f"Iniciando sección: {seccion}")
            productos = self.scrapear_seccion(url, seccion)
            todas_columnas = columnas_base + ["modelo"]
            df = pd.DataFrame(productos)
            df = normalizar_columnas(df, columnas=todas_columnas)
            filename = f"productos_sportingio_{self.session_id}_{seccion.lower()}.xlsx"
            self.export_to_excel(df, filename)
            self.send_alert(f"✅ Sección {seccion} finalizada: {len(df)} productos")
        self.exportar_combinado()
        self.close_browser()

    def scrapear_seccion(self, url_base, seccion):
        max_reintentos = 3
        for intento in range(1, max_reintentos + 1):
            try:
                self.driver.get(url_base)
                time.sleep(self.wait_time)

                # 1) Cargar todo (“scroll” + “mostrar más”)
                while True:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(self.wait_time)

                    try:
                        btn = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "div.vtex-search-result-3-x-buttonShowMore button.vtex-button"
                        )
                        if not btn.is_displayed():
                            raise NoSuchElementException()

                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        try:
                            btn.click()
                        except ElementClickInterceptedException:
                            self.driver.execute_script("arguments[0].click();", btn)

                        self.logger.info("➕ Pulsado 'Mostrar más', cargando siguientes…")
                        time.sleep(self.wait_time)
                        continue

                    except NoSuchElementException:
                        self.logger.info("✅ No hay más productos para cargar.")
                        break

                # 2) Parsear todos los productos ya cargados
                html = self.driver.page_source
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select("div.vtex-search-result-3-x-galleryItem")
                self.logger.info(f"📦 Total de productos detectados en grid: {len(items)}")

                productos_totales = []
                for block in items:
                    prod = self.parsear_producto(block, seccion)
                    if prod:
                        productos_totales.append(prod)

                return productos_totales

            except Exception as e:
                self.logger.warning(
                    f"⚠️ Error en scrapear_seccion '{seccion}' (intento {intento}/{max_reintentos}): {e}"
                )
                time.sleep(self.wait_time)

        # Si llegamos aquí, los reintentos fallaron
        error_msg = f"❌ Fallo definitivo al scrapear la sección {seccion} tras {max_reintentos} intentos."
        self.logger.error(error_msg)
        self.send_alert(error_msg)
        return []

    def parsear_producto(self, soup, seccion):
        try:
            a = soup.select_one("a.sportingio-product-summary-0-x-clearLink")
            href = a["href"] if a and a.has_attr("href") else ""
            pid = href.rstrip("/").split("/")[-1] if href else "N/A"
            link = f"https://www.sporting.com.ar{href}" if href else "N/A"

            nombre = (
                soup.select_one("span.sportingio-product-summary-0-x-brandName")
                .get_text(strip=True) if soup.select_one("span.sportingio-product-summary-0-x-brandName")
                else "N/A"
            )

            imagen = (
                soup.select_one("img.sportingio-product-summary-0-x-imageNormal")["src"]
                if soup.select_one("img.sportingio-product-summary-0-x-imageNormal")
                else "N/A"
            )

            precio_anterior = (
                soup.select_one("span.vtex-product-price-1-x-listPriceValue")
                .get_text(strip=True) if soup.select_one("span.vtex-product-price-1-x-listPriceValue")
                else "N/A"
            )
            precio = (
                soup.select_one("span.vtex-product-price-1-x-sellingPriceValue")
                .get_text(strip=True) if soup.select_one("span.vtex-product-price-1-x-sellingPriceValue")
                else "N/A"
            )
            descuento = (
                soup.select_one("span.vtex-product-price-1-x-savingsPercentage")
                .get_text(strip=True) if soup.select_one("span.vtex-product-price-1-x-savingsPercentage")
                else "N/A"
            )
            cuotas = (
                soup.select_one(".sportingio-store-components-1-x-container_installments")
                .get_text(strip=True) if soup.select_one(".sportingio-store-components-1-x-container_installments")
                else "N/A"
            )

            # visita detalle para extraer "Modelo"
            modelo = "N/A"
            if link != "N/A":
                current = self.driver.current_url
                self.driver.get(link)
                time.sleep(self.wait_time)
                detail = BeautifulSoup(self.driver.page_source, "html.parser")
                m_el = detail.select_one(
                    "div.sportingio-store-components-1-x-customSpecificationsContent--modelo "
                    "span.sportingio-store-components-1-x-customSpecificationsValue"
                )
                if m_el:
                    modelo = m_el.get_text(strip=True)
                # volvemos al listado
                self.driver.get(current)
                time.sleep(1)

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
                "tags": "N/A",
                "hora_inicio": "",
                "hora_fin": "",
                "talles": "N/A",
                "tipo_producto": inferir_categoria(nombre),
                "modelo": modelo,
                "nombre_pagina": "SportingIO",
            }

        except Exception as e:
            self.logger.error(f"Error parseando SportingIO ({seccion}): {e}")
            return None
