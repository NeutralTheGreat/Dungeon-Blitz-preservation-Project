import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from globals import PORT_HTTP, HOST

def start_static_server(
    host: str = HOST,
    port: int = PORT_HTTP,
    directory: str = "content/localhost"
):
    class FlashSafeHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError):
                pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        #def log_message(self, format, *args):
            #return

    httpd = ThreadingHTTPServer((host, port), FlashSafeHandler)

    thread = threading.Thread(
        target=httpd.serve_forever,
        name="StaticHTTPServer",
        daemon=True
    )
    thread.start()
    return httpd
