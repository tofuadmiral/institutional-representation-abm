"""One POST only, recording Retry-After for a separately bounded controller.

No retries, provider/model fallback, key lookup or calls occur on import.
The old transmitter and every frozen source remain unchanged.
"""
import time
import urllib.error
import urllib.request

from paper3.hosted_reasoning_calls import safe_error_body, t


def transmit(wire, secret):
    out = dict(started_unix=time.time(), http_status=None, generation_header=None,
        lines=[], byte_count=0, first_line_unix=None, last_line_unix=None,
        error_type=None, http_error_body=None, http_error_body_truncated=False,
        error_body_redacted=False, retry_after=None)
    request = urllib.request.Request(t.URL, data=wire.encode(), method="POST",
        headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"})
    try:
        with t.opener().open(request, timeout=900) as response:
            out.update(http_status=response.status, headers_unix=time.time(),
                generation_header=response.headers.get("X-Generation-Id"),
                retry_after=response.headers.get("Retry-After"))
            for raw in response:
                now = time.time()
                if out["first_line_unix"] is None:
                    out["first_line_unix"] = now
                out["last_line_unix"] = now
                out["byte_count"] += len(raw)
                out["lines"].append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
    except urllib.error.HTTPError as exc:
        out.update(http_status=exc.code, error_type="HTTPError",
            generation_header=exc.headers.get("X-Generation-Id") if exc.headers else None,
            retry_after=exc.headers.get("Retry-After") if exc.headers else None)
        try:
            raw = exc.read(4097)
            out["http_error_body"], out["error_body_redacted"] = safe_error_body(raw[:4096], secret)
            out["http_error_body_truncated"] = len(raw) > 4096
        except Exception as error:
            out["http_error_body_read_error"] = type(error).__name__
        finally:
            exc.close()
    except Exception as error:
        out["error_type"] = type(error).__name__
    out.update(ended_unix=time.time(), line_count=len(out["lines"]))
    out, hit = t.redact(out, secret)
    out["secret_redacted"] = hit or out["error_body_redacted"]
    return out
