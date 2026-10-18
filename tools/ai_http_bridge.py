"""Loopback-only HTTP transport for DST's QueryServer (Python standard library)."""
import argparse
import ipaddress
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_INPUT_BYTES = 1024 * 1024
UPSTREAM_TIMEOUT = 45


def completion_url(base_url, api_format="chat_completions"):
    """Accept a server root, API prefix, or complete completion endpoint."""
    if not isinstance(base_url, str):
        raise ValueError("invalid base URL")
    parsed = urlsplit(base_url.strip())
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("invalid base URL")
    # Accessing port validates malformed/non-numeric ports before urllib uses it.
    parsed.port
    path = parsed.path.rstrip("/")
    endpoint = "/responses" if api_format == "responses" else "/chat/completions"
    for known_endpoint in ("/responses", "/chat/completions"):
        if known_endpoint in path and (known_endpoint != endpoint or not path.endswith(endpoint)):
            raise ValueError("endpoint does not match API format")
    if not path:
        path = "/v1" + endpoint
    elif not path.endswith(endpoint):
        path += endpoint
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class InvalidField(ValueError):
    """A validation error containing only a fixed field name."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward credentials to a redirected host.
        return None


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status, message):
        self._reply(status, json.dumps({"error": {"message": message}}).encode("utf-8"))

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b'{"ok":true}')
        else:
            self._error(404, "unknown endpoint")

    def do_POST(self):
        if self.path != "/complete":
            self._error(404, "unknown endpoint")
            return
        if self.headers.get("Transfer-Encoding") is not None:
            self._error(400, "transfer encoding is unsupported")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._error(400, "content length is required")
            return
        if length < 1 or length > MAX_INPUT_BYTES:
            self._error(413, "request must contain at most 1 MiB")
            return
        self.connection.settimeout(UPSTREAM_TIMEOUT)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete request")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("invalid request")
            api_format = data.get("api_format", "chat_completions")
            if api_format not in ("chat_completions", "responses"):
                raise InvalidField("invalid api_format")
            try:
                url = completion_url(data.get("base_url"), api_format)
            except (ValueError, TypeError, UnicodeError):
                raise InvalidField("invalid base_url") from None
            api_key = data.get("api_key")
            if isinstance(api_key, str):
                api_key = api_key.strip()
            if (not isinstance(api_key, str) or not api_key
                    or any(ord(char) < 32 or ord(char) > 126 for char in api_key)):
                raise InvalidField("invalid api_key")
            if not isinstance(data.get("model"), str) or not data["model"].strip():
                raise InvalidField("invalid model")
            if not isinstance(data.get("messages"), list):
                raise InvalidField("invalid messages")
            payload = {key: value for key, value in data.items()
                       if key in ("model", "messages", "temperature", "max_tokens", "response_format")}
            payload["model"] = payload["model"].strip()
            if api_format == "responses":
                payload["input"] = payload.pop("messages")
                payload.pop("temperature", None)
                if "max_tokens" in payload:
                    payload["max_output_tokens"] = payload.pop("max_tokens")
                if "response_format" in payload:
                    payload["text"] = {"format": payload.pop("response_format")}
                payload.update(store=False, stream=False)
            encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        except InvalidField as error:
            self._error(400, str(error))
            return
        except (ValueError, TypeError, UnicodeError):
            self._error(400, "invalid completion request")
            return
        except (TimeoutError, OSError):
            self._error(408, "request read timed out or failed")
            return
        request = Request(url, data=encoded, headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }, method="POST")
        try:
            with build_opener(NoRedirect()).open(request, timeout=UPSTREAM_TIMEOUT) as response:
                body = response.read()
            decoded = json.loads(body)
            if not isinstance(decoded, dict):
                raise ValueError("invalid upstream JSON")
            if decoded.get("error") is not None:
                self._error(502, "upstream reported API error")
                return
        except HTTPError as error:
            status = error.code
            error.close()
            self._error(502, "upstream returned HTTP " + str(status))
            return
        except (ValueError, UnicodeError):
            self._error(502, "upstream returned invalid JSON")
            return
        except (TimeoutError, socket.timeout):
            self._error(504, "upstream request timed out")
            return
        except (URLError, OSError):
            self._error(502, "upstream connection failed")
            return
        # DST's decoder does not implement JSON Unicode escapes. Normalize both
        # the envelope and model-generated JSON content using real UTF-8 text.
        try:
            if api_format == "responses":
                if decoded.get("status") == "failed":
                    self._error(502, "upstream response failed")
                    return
                if decoded.get("status") != "completed":
                    self._error(502, "upstream response incomplete")
                    return
                chunks = []
                output = decoded.get("output", [])
                if not isinstance(output, list):
                    raise ValueError("invalid output")
                for item in output:
                    if not isinstance(item, dict) or item.get("type") != "message":
                        continue
                    content = item.get("content", [])
                    if not isinstance(content, list):
                        raise ValueError("invalid message content")
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "refusal":
                            self._error(502, "upstream response refused")
                            return
                        if (isinstance(part, dict) and part.get("type") == "output_text"
                                and isinstance(part.get("text"), str)):
                            chunks.append(part["text"])
                if not "".join(chunks).strip():
                    self._error(502, "upstream response contained no output text")
                    return
                decoded = {"choices": [{"message": {
                    "role": "assistant", "content": "".join(chunks)}}]}
            choices = decoded.get("choices")
            for choice in choices if isinstance(choices, list) else ():
                message = choice.get("message") if isinstance(choice, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str):
                    try:
                        document = json.loads(content)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(document, dict):
                        message["content"] = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
            body = json.dumps(decoded, ensure_ascii=False).encode("utf-8")
        except (ValueError, UnicodeError):
            self._error(502, "upstream returned invalid JSON")
            return
        self._reply(200, body)


def create_server(host="127.0.0.1", port=17893):
    """Create an IPv4 HTTP server only on a numeric loopback address."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("bind address must be an IPv4 loopback address") from None
    if address.version != 4 or not address.is_loopback:
        raise ValueError("bind address must be an IPv4 loopback address")
    return ThreadingHTTPServer((str(address), port), BridgeHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=17893)
    parser.add_argument("--host", default="127.0.0.1", help="numeric IPv4 loopback address")
    args = parser.parse_args()
    try:
        server = create_server(args.host, args.port)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print("DST AI bridge listening on http://%s:%d" % server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
