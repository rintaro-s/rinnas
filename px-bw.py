import http.server
import socketserver

PORT = 8020
DIRECTORY = "php-proxy"

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"Serving {DIRECTORY} at port {PORT}")
    httpd.serve_forever()
