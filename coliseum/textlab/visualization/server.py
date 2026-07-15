"""Loopback-only, capability-scoped HTTP service for read-only replay views."""
from __future__ import annotations

import argparse
import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .errors import VisualizationError, refuse
from .evidence import API_VERSION, ReplayVerification, RunRoot, load_validated_run, verify_replay
from .view_model import build_view_model, run_card

_STATIC = {
    "": ("index.html", "text/html; charset=utf-8"),
    "static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "static/playback.js": ("playback.js", "text/javascript; charset=utf-8"),
    "static/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class VisualizationService:
    """Immutable launch configuration and validated run cache."""

    def __init__(self, run_root, perspective, actor_key=None, verify=False,
                 capability=None):
        if perspective not in ("actor", "privileged"):
            refuse("invalid_perspective", "service mode must be actor or privileged")
        if perspective == "actor" and (not isinstance(actor_key, str) or not actor_key):
            refuse("actor_required", "actor mode requires one pinned observer key")
        if perspective == "privileged" and actor_key is not None:
            refuse("invalid_configuration", "privileged mode cannot pin an actor")
        self.root = RunRoot(run_root)
        self.perspective = perspective
        self.actor_key = actor_key
        self.verify_at_launch = bool(verify)
        self.capability = capability or secrets.token_urlsafe(32)
        if not isinstance(self.capability, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{43,128}", self.capability):
            refuse("invalid_capability", "capability must carry at least 256 bits")
        self.runs = {}
        self.replay = {}
        self.refused_count = 0
        self.static_root = Path(__file__).with_name("static")
        self.expected_host = None
        self._discover()

    def _discover(self):
        for run_id in self.root.list_ids():
            try:
                validated = load_validated_run(self.root, run_id)
                if self.perspective == "actor" and \
                        self.actor_key not in validated.run["observers"]:
                    continue
                replay = (verify_replay(validated) if self.verify_at_launch else
                          ReplayVerification("unverified", "not requested at launch"))
                self.runs[run_id] = validated
                self.replay[run_id] = replay
            except Exception:
                self.refused_count += 1

    def cards(self):
        return [run_card(self.runs[run_id], self.perspective, self.actor_key,
                         self.replay[run_id])
                for run_id in sorted(self.runs)]

    def view(self, run_id):
        validated = self.runs.get(run_id)
        if validated is None:
            refuse("run_unavailable", "run is absent or unavailable in this perspective")
        return build_view_model(validated, self.perspective, self.actor_key,
                                self.replay[run_id])


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentColiseumVisualization/1"
        sys_version = ""

        def log_message(self, _format, *args):
            return

        def _headers(self, status, content_type, length):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.end_headers()

        def _send(self, status, body, content_type):
            self._headers(status, content_type, len(body))
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, status, code):
            body = _json_bytes({"api_version": API_VERSION,
                                "error": {"code": code}})
            self._send(status, body, "application/json; charset=utf-8")

        def _authorized_path(self):
            host = self.headers.get("Host")
            if host != service.expected_host:
                self._error(421, "unexpected_host")
                return None
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment or "%" in parsed.path or "\\" in parsed.path:
                self._error(400, "invalid_path")
                return None
            prefix = f"/{service.capability}/"
            if not parsed.path.startswith(prefix):
                self._error(404, "not_found")
                return None
            return parsed.path[len(prefix):]

        def _handle(self):
            relative = self._authorized_path()
            if relative is None:
                return
            if relative in _STATIC:
                name, content_type = _STATIC[relative]
                try:
                    body = (service.static_root / name).read_bytes()
                except OSError:
                    self._error(500, "static_unavailable")
                    return
                self._send(200, body, content_type)
                return
            if relative == "api/v1/health":
                body = _json_bytes({
                    "api_version": API_VERSION, "status": "ready",
                    "perspective": service.perspective,
                    "run_count": len(service.runs),
                })
                self._send(200, body, "application/json; charset=utf-8")
                return
            if relative == "api/v1/runs":
                body = _json_bytes({"api_version": API_VERSION,
                                    "perspective": service.perspective,
                                    "runs": service.cards()})
                self._send(200, body, "application/json; charset=utf-8")
                return
            marker = "api/v1/runs/"
            if relative.startswith(marker) and relative.endswith("/view"):
                run_id = relative[len(marker):-len("/view")]
                try:
                    RunRoot._valid_id(run_id)
                    body = _json_bytes(service.view(run_id))
                except VisualizationError as exc:
                    status = 404 if exc.code in ("run_unavailable", "unsafe_run_id") else 422
                    self._error(status, exc.code)
                    return
                self._send(200, body, "application/json; charset=utf-8")
                return
            self._error(404, "not_found")

        def do_GET(self):
            self._handle()

        def do_HEAD(self):
            self._handle()

        def _read_only(self):
            self._error(405, "read_only_service")

        do_POST = do_PUT = do_PATCH = do_DELETE = _read_only

    return Handler


def serve(service, host="127.0.0.1", port=0):
    if host != "127.0.0.1":
        refuse("non_loopback_host", "MVP service binds only 127.0.0.1")
    if type(port) is not int or not 0 <= port <= 65535:
        refuse("invalid_port", "port must be an integer from 0 through 65535")
    server = ThreadingHTTPServer((host, port), make_handler(service))
    actual_port = server.server_address[1]
    service.expected_host = f"{host}:{actual_port}"
    return server, f"http://{service.expected_host}/{service.capability}/"


def parser():
    result = argparse.ArgumentParser(
        prog="python -m coliseum.textlab.visualization",
        description="Serve validated Agent Coliseum replays without mutation or inference.")
    result.add_argument("--run-root", required=True,
                        help="Pinned local directory containing spatial run directories")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--actor", metavar="OBSERVER_KEY",
                      help="Serve only this actor's recorded observation artifacts")
    mode.add_argument("--privileged", action="store_true",
                      help="Explicitly serve validated global research state")
    result.add_argument("--verify-replay", action="store_true",
                        help="Run provider-free byte replay gates before serving")
    result.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    result.add_argument("--port", default=0, type=int)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    perspective = "privileged" if args.privileged else "actor"
    service = VisualizationService(args.run_root, perspective, args.actor,
                                   args.verify_replay)
    server, url = serve(service, args.host, args.port)
    print(f"Agent Coliseum replay viewer: {url}", flush=True)
    print(f"Perspective: {perspective}; admitted runs: {len(service.runs)}; "
          f"refused directories: {service.refused_count}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
