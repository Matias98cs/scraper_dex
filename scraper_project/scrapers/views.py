from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.management import call_command
import threading, logging
import time
from rest_framework import status
from io import StringIO

logger = logging.getLogger(__name__)

@api_view(['GET'])
def test_connection(request):
    return Response({'message': 'Connection successful'})


@api_view(['POST'])
def run_scraper_dash(request):
    """
    Espera un JSON en el body con:
    {
      "threads": <número de hilos opcional, por defecto 4>,
      "output": "<nombre_de_archivo_salida opcional>",
      "local": <booleano opcional para usar driver local>
    }
    """
    data = request.data or {}
    try:
        threads = int(data.get('threads', 4))
    except (ValueError, TypeError):
        threads = 4

    output_name = data.get('output')
    local_execution = bool(data.get('local', False))

    def _run():
        try:
            logger.info(
                f"Thread-RunDashScraper: arrancando management command "
                f"con threads={threads}, output={output_name}, local={local_execution}"
            )

            cmd_args = ["--threads", str(threads)]
            if local_execution:
                cmd_args.append("--local")
            if output_name:
                cmd_args += ["--output", output_name]

            call_command("dash_2", *cmd_args)
            time.sleep(1)
            logger.info("Thread-RunDashScraper: el command finalizó o tiró error")
        except Exception:
            logger.exception("Hubo un error al ejecutar el scraper")

    t = threading.Thread(
        target=_run,
        name="Thread-RunDashScraper",
        daemon=False
    )
    t.start()

    return Response({
        'status': 'started',
        'threads': threads,
        'output': output_name,
        'local': local_execution,
        'message': 'Se ha disparado el scraper en background.'
    })


@api_view(['POST'])
def run_dash_more_threads(request):
    def _run():
        try:
            logger.info("Thread-RunDashMoreThreads: arrancando management command sin parámetros")
            call_command("run_dash_more_threads")
            time.sleep(1)
            logger.info("Thread-RunDashMoreThreads: el comando finalizó o tiró error")
        except Exception:
            logger.exception("Hubo un error al ejecutar run_dash_more_threads")

    t = threading.Thread(
        target=_run,
        name="Thread-RunDashMoreThreads",
        daemon=False
    )
    t.start()

    return Response({
        'status': 'started',
        'message': "Se ha disparado 'run_dash_more_threads' en background."
    })



ALLOWED_COMMANDS = {
    "populate_dexter_codes": [],
    "import_productos_dash": [],
    "import_productos_dexter": [],
    "import_productos_grid": [],
    "import_productos_moov": [],
    "import_productos_solodeportes": [],
    "import_productos_solourbano": [],
    "import_productos_stockcenter": [],
    "import_productos_sporting": [],
    "import_productos_sportline": [],
}

@api_view(['POST'])
def run_management_command(request):
    command = request.data.get('command')
    extra_args = request.data.get('args', [])
    if not command or command not in ALLOWED_COMMANDS:
        return Response(
            {"detail": "Comando no permitido"},
            status=status.HTTP_400_BAD_REQUEST
        )

    out = StringIO()
    try:
        call_command(command, *ALLOWED_COMMANDS[command], *extra_args, stdout=out)
    except Exception as e:
        return Response(
            {"detail": f"Error ejecutando el comando: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(
        {"output": out.getvalue()},
        status=status.HTTP_200_OK
    )