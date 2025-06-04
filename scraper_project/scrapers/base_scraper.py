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

    
    def close_browser(self):
        if self.driver:
            self.driver.quit()

    def send_alert(self, message):
        send_alert_message(message)

    def export_to_json(self, data: list, filename: str) -> str:
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"✅ Exported {len(data)} items to {filepath}")
        return filepath
    
    def exportar_combinado_json(self, all_data: list, filename: str) -> str:
        return self.export_to_json(all_data, filename)
    
    def run(self):
        raise NotImplementedError("Each scraper must implement the run method.")
