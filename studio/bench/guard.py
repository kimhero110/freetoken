from .transport import resolve

def ssrf_guard(base_url):
    resolve(base_url)
