import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_ALERT_USERS = os.getenv("SLACK_ALERT_USERS", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

client = WebClient(token=SLACK_TOKEN)

def setup_logger(name, output_dir="logs"):
    os.makedirs(output_dir, exist_ok=True)
    log_file = os.path.join(output_dir, f"log_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger

def send_alert_message(message):
    try:
        # Enviar al canal
        # if SLACK_CHANNEL:
        #     client.chat_postMessage(channel=SLACK_CHANNEL, text=message)
        #     print(f"✅ Alerta enviada al canal: {SLACK_CHANNEL}")

        # Enviar a usuarios privados
        user_ids = [uid.strip() for uid in SLACK_ALERT_USERS.split(",") if uid.strip()]
        for user_id in user_ids:
            client.chat_postMessage(channel=user_id, text=message)
            print(f"✅ Alerta enviada a usuario: {user_id}")

    except SlackApiError as e:
        print(f"❌ Error al enviar alerta a Slack: {e.response['error']}")


def initialize_driver_remote():

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

def initialize_driver_local():
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(1)
    return driver
