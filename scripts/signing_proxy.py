#!/usr/bin/env python3
"""Local CloudStack signing proxy for Swagger UI "Try it out".

Browser -> http://localhost:8081/client/api/<command>?... -> this proxy
  * drops any apikey / signature / sessionkey sent by the browser
  * takes `command` from the query string (or the last path segment)
  * signs the request with HmacSHA1 using your API + secret key
  * forwards it to the real management server and returns the response
    with CORS headers, so the browser accepts it.

Your secret key never reaches the browser. Standard library only.

Configuration (environment variables win over the ini file):
  CS_ENDPOINT    e.g. http://10.0.0.10:8080/client/api
  CS_API_KEY
  CS_SECRET_KEY
  CS_CONFIG      path to an ini file (default ~/.cloudstack.ini, section [cloudstack]
                 with endpoint / key / secret, the same file the `cs` CLI uses)
  PROXY_HOST     default 127.0.0.1 (use 0.0.0.0 inside a container)
  PROXY_PORT     default 8081
  CS_VERIFY_TLS  set to "false" to accept self-signed management-server certs
"""
import base64
import configparser
import hashlib
import hmac
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SKIP = {"apikey", "signature", "sessionkey", "response"}


def load_config():
    cfg = {"endpoint": None, "key": None, "secret": None}
    path = os.path.expanduser(os.environ.get("CS_CONFIG", "~/.cloudstack.ini"))
    if os.path.exists(path):
        ini = configparser.ConfigParser()
        ini.read(path)
        if ini.has_section("cloudstack"):
            for k in cfg:
                cfg[k] = ini.get("cloudstack", k, fallback=None)
    cfg["endpoint"] = os.environ.get("CS_ENDPOINT") or cfg["endpoint"]
    cfg["key"] = os.environ.get("CS_API_KEY") or cfg["key"]
    cfg["secret"] = os.environ.get("CS_SECRET_KEY") or cfg["secret"]
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        sys.exit(f"signing_proxy: missing {', '.join(missing)} "
                 "(set CS_ENDPOINT / CS_API_KEY / CS_SECRET_KEY or ~/.cloudstack.ini)")
    cfg["endpoint"] = cfg["endpoint"].rstrip("/")
    return cfg


CFG = load_config()
SSL_CTX = None
if os.environ.get("CS_VERIFY_TLS", "true").lower() == "false":
    SSL_CTX = ssl._create_unverified_context()


def enc(v):
    # Same as JS encodeURIComponent + escaping !'()*  -> spaces become %20
    return urllib.parse.quote(v, safe="-_.~")


def signed_query(params):
    params = {k: v for k, v in params.items() if k.lower() not in SKIP and v != ""}
    params["response"] = "json"
    params["apikey"] = CFG["key"]
    query = "&".join(f"{k}={enc(params[k])}" for k in sorted(params, key=str.lower))
    digest = hmac.new(CFG["secret"].encode(), query.lower().encode(), hashlib.sha1).digest()
    return query + "&signature=" + enc(base64.b64encode(digest).decode())


class Handler(BaseHTTPRequestHandler):
    server_version = "cs-signing-proxy"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        if "command" not in params and segment not in ("", "api"):
            params["command"] = segment
        if "command" not in params:
            return self._send(400, b'{"error":"no command given"}')

        url = f"{CFG['endpoint']}?{signed_query(params)}"
        try:
            with urllib.request.urlopen(url, timeout=120, context=SSL_CTX) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except Exception as e:  # network / TLS errors
            status, body = 502, ('{"error":%r}' % str(e)).replace("'", '"').encode()
        self._send(status, body)

    def _send(self, status, body):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Log the command only; never the signed URL
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        cmd = q.get("command") or self.path.split("?")[0].rsplit("/", 1)[-1]
        print(f"{self.command} {cmd} -> {args[1] if len(args) > 1 else ''}", file=sys.stderr, flush=True)


def main():
    host = os.environ.get("PROXY_HOST", "127.0.0.1")
    port = int(os.environ.get("PROXY_PORT", "8081"))
    print(f"CloudStack signing proxy on http://{host}:{port}/client/api -> {CFG['endpoint']}",
          flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
