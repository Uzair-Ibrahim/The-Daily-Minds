"""DNS-pinned HTTP transport: TLS/Host retain the publisher name, TCP uses vetted IPs."""
import asyncio
import ipaddress
import socket
import ssl

import httpcore
import httpx


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, backend=None, lookup=None):
        self.backend = backend or httpcore.AnyIOBackend()
        self.lookup = lookup

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        lookup = self.lookup or asyncio.get_running_loop().getaddrinfo
        async with asyncio.timeout(timeout or 4):
            addresses = await lookup(host, port, type=socket.SOCK_STREAM)
            ips = list(dict.fromkeys(row[4][0] for row in addresses))
            if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                raise OSError('Non-public destination rejected')
            for ip in ips[:3]:
                try:
                    return await self.backend.connect_tcp(ip, port, timeout=timeout,
                                                          local_address=local_address, socket_options=socket_options)
                except (OSError, httpcore.ConnectError, httpcore.ConnectTimeout):
                    continue
            raise OSError('Public destination unavailable')

    async def connect_unix_socket(self, *args, **kwargs):
        raise OSError('Unix destinations rejected')

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class CoreStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        async for data in self.stream:
            yield data

    async def aclose(self):
        await self.stream.aclose()


class PublicTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.pool = httpcore.AsyncConnectionPool(ssl_context=ssl.create_default_context(),
            network_backend=PublicNetworkBackend(), max_connections=3, max_keepalive_connections=0)

    async def handle_async_request(self, request):
        response = await self.pool.handle_async_request(httpcore.Request(
            method=request.method, url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host,
            port=request.url.port, target=request.url.raw_path), headers=request.headers.raw,
            content=request.stream, extensions=request.extensions))
        return httpx.Response(response.status, headers=response.headers, stream=CoreStream(response.stream),
                              extensions=response.extensions)

    async def aclose(self):
        await self.pool.aclose()
