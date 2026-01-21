from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class MockGatewayHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/send":
            self._send_json(404, {"status": "error", "detail": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body_text = ""
        if content_length:
            body = self.rfile.read(content_length)
            try:
                body_text = body.decode("utf-8", errors="replace")
            except Exception:
                body_text = repr(body)

        if body_text:
            print(f"Mock gateway received: {body_text}")

        self._send_json(200, {"status": "ok"})


def main() -> None:
    server = HTTPServer(("127.0.0.1", 3000), MockGatewayHandler)
    print("Mock WhatsApp gateway listening on http://127.0.0.1:3000")
    server.serve_forever()


if __name__ == "__main__":
    main()
