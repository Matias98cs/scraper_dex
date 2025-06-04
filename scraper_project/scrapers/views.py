from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.management import call_command
import threading, logging
import time

logger = logging.getLogger(__name__)

@api_view(['GET'])
def test_connection(request):
    return Response({'message': 'Connection successful'})


@api_view(['GET'])
def run_scraper_dash(request):
    def _run():
        try:
            logger.info("Thread-RunDashScraper: arrancando management command")
            call_command("run_dash_more_threads", "--headless")
            time.sleep(1)  # <-- espera breve para que el logging se vacíe
            logger.info("Thread-RunDashScraper: el command finalizó o tiró error")
        except Exception:
            logger.exception("Hubo un error al ejecutar el scraper")

    # Si quitas daemon=True, te aseguras de que el hilo siga activo 
    # incluso después de responder la petición HTTP.
    t = threading.Thread(target=_run, name="Thread-RunDashScraper", daemon=False)
    t.start()

    return Response({
        'status': 'started',
        'message': 'Se ha disparado el scraper en background.'
    })
