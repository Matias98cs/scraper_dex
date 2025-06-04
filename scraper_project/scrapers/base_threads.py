import os
import threading
import time
from queue import Queue, Empty
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

class ThreadedDriverPool:
    """
    Clase auxiliar que maneja un pool de WebDrivers y hilos para procesar una lista de items,
    cada uno con un enlace (o cualquier campo que el process_fn necesite).
    
    Uso:
      pool = ThreadedDriverPool(max_threads=4)
      pool.setup_driver_pool()
      resultados = pool.run_threaded(items, process_fn)
      pool.close_driver_pool()
    
    - items: lista de diccionarios (o cualquier objeto mutable) que incluyan la clave "link"
             (o cualquier campo que el process_fn quiera usar).
    - process_fn: función(driver, item) que recibe un WebDriver y el diccionario item,
                  navega/extráe/actualiza item in-place y/o devuelve un dict con nuevos campos.
    """
    def __init__(self, max_threads=4):
        self.max_threads = max_threads
        self.driver_pool = Queue(maxsize=self.max_threads)

    def _init_driver(self):
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(1)
        return driver

    def setup_driver_pool(self):
        for _ in range(self.max_threads):
            drv = self._init_driver()
            self.driver_pool.put(drv)

    def close_driver_pool(self):
        while not self.driver_pool.empty():
            try:
                drv = self.driver_pool.get_nowait()
                drv.quit()
            except Empty:
                break
            except Exception:
                pass

    def run_threaded(self, items: list, process_fn):
        """
        Procesa 'items' en paralelo usando hilos y el pool de drivers.
        
        - items: lista de dicts (o cualquier objeto mutable) que contengan la clave "link"
                 (o el campo que necesite process_fn).
        - process_fn: función(driver, item), donde:
            * driver: WebDriver sacado del pool
            * item: el diccionario a procesar en ese hilo
            * process_fn puede actualizar item in-place (p. ej. item["modelo_id"] = ...)
              o devolver un dict con nuevos campos (que luego se mezclarán en item).
        
        Devuelve: lista de items actualizados (en el mismo orden en que se entregan los hilos,
                  sin garantizar orden original; si hace falta mantener orden, post-procesar).
        """
        total = len(items)
        # Asumimos que setup_driver_pool() ya fue llamado
        task_q = Queue()
        for idx, it in enumerate(items, start=1):
            task_q.put((idx, it))

        results = []
        lock = threading.Lock()

        def worker():
            tname = threading.current_thread().name
            while True:
                try:
                    idx, itm = task_q.get_nowait()
                except Empty:
                    break

                try:
                    driver = self.driver_pool.get()
                    retorno = process_fn(driver, itm)
                    if isinstance(retorno, dict):
                        itm.update(retorno)
                except Exception as e:
                    # Si process_fn falla, marcamos el error en el item
                    itm.setdefault("error", str(e))
                finally:
                    # Siempre devolvemos el driver al pool
                    try:
                        self.driver_pool.put(driver)
                    except Exception:
                        pass

                    with lock:
                        results.append(itm)
                    task_q.task_done()

        threads = []
        for i in range(self.max_threads):
            t = threading.Thread(target=worker, name=f"PoolHilo_{i+1}")
            threads.append(t)
            t.start()

        task_q.join()
        return results
