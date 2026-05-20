"""Local mock ComfyUI server for tests.

Implements just enough of the real API for the client and AI source to
complete a generation lifecycle:

* ``POST /prompt``      → registers a prompt_id, returns it
* ``GET  /history/<id>``→ returns a completed-job record with one output file
* ``GET  /view``        → streams the canned video bytes

The "video" is a small chunk of bytes (not a real container); the wrapper
doesn't decode it, so this is sufficient for the disk-write + meta-validation
contract.

Behaviour switches via class attributes set by tests:
* ``fail_on_submit``: every /prompt returns 500
* ``fail_n_polls``: first N /history calls return 500 (simulates spot-blip
  transient transport errors)
* ``node_errors``: returned as ``node_errors`` in /prompt response
* ``execution_error``: returned in /history status messages
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.parse
import uuid


class MockComfy:
    """Stateful fake. Tests reach into the class to flip switches."""

    VIDEO_BYTES = b"FAKE_MP4_BYTES_" + b"\x00\x01" * 4096
    fail_on_submit = False
    fail_n_polls = 0
    node_errors: dict = {}
    execution_error: list | None = None

    _polls_so_far = 0
    _submitted: dict[str, dict] = {}

    @classmethod
    def reset(cls) -> None:
        cls.fail_on_submit = False
        cls.fail_n_polls = 0
        cls.node_errors = {}
        cls.execution_error = None
        cls._polls_so_far = 0
        cls._submitted = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/prompt":
            if MockComfy.fail_on_submit:
                self.send_response(500)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)  # body discarded
            prompt_id = uuid.uuid4().hex[:16]
            MockComfy._submitted[prompt_id] = {"completed": False, "polls": 0}
            resp = {"prompt_id": prompt_id, "number": 1, "node_errors": MockComfy.node_errors}
            self._send_json(200, resp)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/history/"):
            prompt_id = self.path.rsplit("/", 1)[-1]
            if MockComfy._polls_so_far < MockComfy.fail_n_polls:
                MockComfy._polls_so_far += 1
                self.send_response(500)
                self.end_headers()
                return
            if prompt_id not in MockComfy._submitted:
                self.send_response(404)
                self.end_headers()
                return
            entry = MockComfy._submitted[prompt_id]
            # Complete on the first successful poll (the client polls fast).
            messages = []
            if MockComfy.execution_error:
                messages = [["execution_error", *MockComfy.execution_error]]
            self._send_json(200, {
                prompt_id: {
                    "status": {
                        "completed": True,
                        "status_str": "success" if not MockComfy.execution_error else "error",
                        "messages": messages,
                    },
                    "outputs": {
                        "8": {
                            "gifs": [
                                {
                                    "filename": f"broll_{prompt_id}.mp4",
                                    "subfolder": "broll",
                                    "type": "output",
                                    "format": "video/h264-mp4",
                                }
                            ]
                        }
                    },
                }
            })
            return
        if self.path.startswith("/view"):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MockComfy.VIDEO_BYTES)))
            self.end_headers()
            self.wfile.write(MockComfy.VIDEO_BYTES)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args, **kwargs) -> None:
        pass

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start() -> tuple[_Server, threading.Thread, str]:
    MockComfy.reset()
    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, thread, f"http://127.0.0.1:{port}"


def stop(server: _Server, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
