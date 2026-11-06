"""A tiny mock OpenAI-compatible server for testing the Agent Studio
pipeline end-to-end without any real API key.

Endpoints: GET /v1/models, POST /v1/chat/completions
Run:  python scripts/mock_openai.py   (listens on 127.0.0.1:8291)
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT = {
    "title": "InsaneVoice Agent Test",
    "scenes": [
        {"narration": "Something insane just landed on your laptop.",
         "visual": {"type": "title", "text": "Something insane is here.",
                    "sub": "made entirely on a laptop"}, "est_seconds": 5},
        {"narration": "Voice DNA measures your pitch, warmth and brightness, "
                      "then names your voice like a species.",
         "visual": {"type": "points", "text": "Voice DNA",
                    "points": ["pitch", "warmth", "brightness"]}, "est_seconds": 8},
        {"narration": "The director studio gives you three takes for every line. "
                      "You pick the winner.",
         "visual": {"type": "quote", "text": "Three takes. One winner.",
                    "sub": "Director's Studio"}, "est_seconds": 8},
        {"narration": "Free, private, and completely yours.",
         "visual": {"type": "end", "text": "InsaneVoice"}, "est_seconds": 4},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send({"object": "list", "data": [{"id": "mock-scripter-1"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.endswith("/chat/completions"):
            user = ""
            for m in body.get("messages", []):
                if m.get("role") == "user":
                    c = m.get("content")
                    user = c if isinstance(c, str) else str(c)
            if "image_url" in user or isinstance(body.get("messages", [{}])[0].get("content"), list):
                self._send({"choices": [{"message": {
                    "role": "assistant",
                    "content": "A paper-textured scene with a warm mood."}}]})
                return
            self._send({"choices": [{"message": {
                "role": "assistant",
                "content": "```json\n" + json.dumps(SCRIPT) + "\n```"}}]})
        else:
            self._send({"error": "not found"}, 404)


if __name__ == "__main__":
    print("mock provider on http://127.0.0.1:8291/v1")
    HTTPServer(("127.0.0.1", 8291), Handler).serve_forever()
