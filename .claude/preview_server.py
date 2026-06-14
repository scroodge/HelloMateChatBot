"""Minimal static file server for Mini App HTML preview."""
import http.server, os
port = int(os.environ.get('PORT', 8081))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'web'))
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=port, bind='127.0.0.1')
