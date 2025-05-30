import os
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from scrapers.utils_scraping import normalizar_columnas
from scrapers.utils import setup_logger, send_alert_message
import json


class BaseScraper:
    def __init__(self, name):
        self.name = name
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = f"outputs/{self.name}"
        os.makedirs(self.output_dir, exist_ok=True)
        self.logger = setup_logger(self.name, self.output_dir)
        self.driver = None

    def setup_browser(self):
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        # options.add_argument("--window-size=1280,720")
        options.add_argument("--headless")  # modo headless
        self.driver = webdriver.Chrome(service=service, options=options)

    def export_to_excel(self, df, filename):
        filepath = os.path.join(self.output_dir, filename)
        df.to_excel(filepath, index=False)
        self.logger.info(f"✅ Exported {len(df)} items to {filepath}")
        return filepath

    def export_to_csv(self, df: pd.DataFrame, filename: str) -> str:
        """
        Guarda el DataFrame como CSV en self.output_dir.
        filename debe terminar en .csv
        """
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)
        self.logger.info(f"✅ Exported {len(df)} items to {filepath}")
        return filepath
    
    def close_browser(self):
        if self.driver:
            self.driver.quit()

    def send_alert(self, message):
        send_alert_message(message)


    def exportar_combinado(self):
        self.logger.info("\n🔄 Buscando archivos individuales para combinar...")
        archivos = [
            f for f in os.listdir(self.output_dir)
            if f.endswith(".xlsx")
            and "combinado" not in f.lower()
            and self.session_id in f
        ]

        if not archivos:
            self.logger.info("🚫 No se encontraron archivos para combinar.")
            return

        combinados = []
        for archivo in archivos:
            self.logger.info(f"➕ Agregando: {archivo}")
            df = pd.read_excel(os.path.join(self.output_dir, archivo))
            combinados.append(df)

        df_final = pd.concat(combinados, ignore_index=True)
        df_final = normalizar_columnas(df_final)

        final_file = os.path.join(self.output_dir, f"productos_{self.name}_combinado_{self.session_id}.xlsx")
        df_final.to_excel(final_file, index=False)

        self.logger.info(f"\n✅ Exportación combinada completa: {final_file}")
        self.send_alert(f"✅ Archivo combinado generado: {final_file}")

    def exportar_combinado_csv(self):
        self.logger.info("🔄 Buscando CSVs individuales para combinar...")
        archivos = [
            f for f in os.listdir(self.output_dir)
            if f.endswith(".csv")
            and "combinado" not in f.lower()
            and self.session_id in f
        ]

        if not archivos:
            self.logger.info("🚫 No se encontraron CSVs para combinar.")
            return

        dfs = []
        for archivo in archivos:
            ruta = os.path.join(self.output_dir, archivo)
            self.logger.info(f"➕ Agregando CSV: {archivo}")
            dfs.append(pd.read_csv(ruta))

        df_final = pd.concat(dfs, ignore_index=True)
        df_final = normalizar_columnas(df_final)

        final_file = os.path.join(
            self.output_dir,
            f"productos_{self.name}_combinado_csv_{self.session_id}.xlsx"
        )
        df_final.to_excel(final_file, index=False)

        self.logger.info(f"✅ Combinado CSV exportado a Excel: {final_file}")

    def export_to_json(self, data: list, filename: str) -> str:
        """
        Guarda la lista de dicts como JSON en self.output_dir.
        filename debe terminar en .json
        """
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"✅ Exported {len(data)} items to {filepath}")
        return filepath
    
    def exportar_combinado_json(self, all_data: list, filename: str) -> str:
        """
        Guarda un solo JSON con todos los items de all_data.
        """
        return self.export_to_json(all_data, filename)
    def run(self):
        raise NotImplementedError("Each scraper must implement the run method.")
