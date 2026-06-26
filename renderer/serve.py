import http.server
import os
import sys
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else '_site'
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8137

class Handler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            fallback = os.path.join(ROOT, '404.html')
            if os.path.isfile(fallback):
                body = open(fallback, 'rb').read()
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)
if __name__ == '__main__':
    with http.server.ThreadingHTTPServer(('', PORT), Handler) as httpd:
        print(f'serving {ROOT} at http://localhost:{PORT}  (404 → 404.html)')
        httpd.serve_forever()
