"""Public HTTPS, pinned DNS, no redirects; bounded streaming response."""
import http.client
import ipaddress
import os
import socket
import ssl
import time
import threading
import urllib.error
from urllib.parse import urlsplit

MAX_BYTES = 4 * 1024 * 1024

def resolve(url):
    p = urlsplit(url)
    if p.username or p.password or p.fragment or p.query or not p.hostname or any(ord(c)<32 for c in url):
        raise ValueError('无效的 API 接入地址')
    local_test = os.getenv('STUDIO_TEST_LOOPBACK') == '1' and p.hostname in ('127.0.0.1', 'localhost')
    if p.scheme != 'https' and not (local_test and p.scheme == 'http'):
        raise ValueError('API 接入地址必须使用 HTTPS')
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme=='https' else 80), type=socket.SOCK_STREAM)
    if not addresses: raise ValueError('无法解析接入地址')
    for _,_,_,_,addr in addresses:
        ip = ipaddress.ip_address(addr[0].split('%')[0])
        if not ip.is_global and not (local_test and ip.is_loopback):
            raise ValueError('不允许访问私有或保留地址')
    return p, addresses[0]

class Response:
    def __init__(self, connection, response, deadline, timer):
        self.connection, self.response, self.deadline = connection, response, deadline
        self.timer = timer
        self.status, self.headers, self.count = response.status, response.headers, 0
    def __enter__(self): return self
    def __exit__(self, *args):
        self.timer.cancel(); self.response.close(); self.connection.close()
    def read(self, size=-1):
        if time.monotonic() > self.deadline: raise TimeoutError('调用超过总时限')
        data = self.response.read(min(MAX_BYTES-self.count+1, size) if size>=0 else MAX_BYTES-self.count+1)
        self.count += len(data)
        if self.count>MAX_BYTES: raise ValueError('响应超过大小限制')
        return data
    def __iter__(self): return self
    def __next__(self):
        if time.monotonic()>self.deadline: raise TimeoutError('流式调用超过总时限')
        line=self.response.readline(min(65537, MAX_BYTES-self.count+1))
        self.count+=len(line)
        if len(line)>65536 or self.count>MAX_BYTES: raise ValueError('流式响应超过大小限制')
        if not line: raise StopIteration
        return line

def urlopen(req, timeout=60):
    p, endpoint=resolve(req.full_url)
    family, socktype, proto, _, address=endpoint
    host=p.hostname;port=p.port or (443 if p.scheme=='https' else 80)
    conn=http.client.HTTPConnection(host, port, timeout=min(timeout,20))
    sock=socket.socket(family,socktype,proto);sock.settimeout(min(timeout,20))
    timer = None
    try:
        sock.connect(address)
        if p.scheme=='https': sock=ssl.create_default_context().wrap_socket(sock,server_hostname=host)
        def expire():
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()
        timer=threading.Timer(timeout,expire);timer.daemon=True;timer.start()
        conn.sock=sock
        headers=dict(req.header_items());headers['Accept-Encoding']='identity'
        conn.request(req.get_method(),p.path+('?' +p.query if p.query else ''),body=req.data,headers=headers)
        response=conn.getresponse()
        if response.status>=300:
            code=response.status;conn.close()
            raise urllib.error.HTTPError(req.full_url,code,'上游请求失败或重定向被禁止',{},None)
        return Response(conn,response,time.monotonic()+timeout,timer)
    except Exception:
        if timer: timer.cancel()
        sock.close();conn.close();raise
