"""HTTP helpers (standard library only).

Python builds from python.org on macOS ship without CA certificates until "Install Certificates.command" is run,
so every request falls back to the system curl when certificate verification fails.
"""

import os
import shutil
import ssl
import subprocess
import urllib.error
import urllib.request

from . import __version__

USER_AGENT = f"internship-finder/{__version__}"
_CONTEXT = ssl.create_default_context()


def _ssl_failure(error):
    return isinstance(error, urllib.error.URLError) and isinstance(error.reason, ssl.SSLError)


def _curl(args):
    if not shutil.which("curl"):
        raise RuntimeError("SSL certificate check failed and curl is not installed. "
                           "Install certificates for this Python (macOS: run 'Install Certificates.command').")
    return subprocess.run(["curl", "-A", USER_AGENT, *args], capture_output=True, check=True).stdout


def fetch_bytes(url, timeout=60):
    """GET a URL and return the raw body. Raises on network errors and HTTP error codes."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_CONTEXT) as response:
            return response.read()
    except urllib.error.URLError as error:
        if not _ssl_failure(error):
            raise
    return _curl(["-sSL", "--fail", "--max-time", str(timeout), url])


def fetch(url, timeout=60):
    """GET a URL and return the body as text."""
    return fetch_bytes(url, timeout).decode("utf-8", errors="replace")


def final_url(url, timeout=20):
    """Follow HTTP redirects (short links such as go.vansh.nyc) and return the address they end at.

    Returns the input unchanged when the link can't be followed.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_CONTEXT) as response:
            return response.geturl()
    except urllib.error.HTTPError as error:
        # The final page refused us (403, 404...), but the error still says where the redirects ended.
        return error.geturl() or url
    except urllib.error.URLError as error:
        if not _ssl_failure(error):
            return url
    except (OSError, ValueError):
        return url
    try:
        out = _curl(["-sSL", "--max-time", str(timeout), "-o", os.devnull, "-w", "%{url_effective}", url])
    except (subprocess.CalledProcessError, RuntimeError):
        return url
    return out.decode().strip() or url
