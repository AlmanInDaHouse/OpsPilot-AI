"""Local byte-forwarding PG proxy: drop a real COMMIT request or its real response."""

import socket
import threading
from contextlib import contextmanager

from sqlalchemy.engine import make_url


@contextmanager
def commit_transport(dsn, committed):
    url = make_url(dsn)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(15)
    armed = threading.Event()
    dropped = threading.Event()
    stopped = threading.Event()
    sockets = []
    threads = []

    def shutdown():
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def serve():
        try:
            client, _ = server.accept()
            upstream = socket.create_connection((url.host, url.port), timeout=5)
            sockets.extend([client, upstream])
            client.settimeout(15)
            upstream.settimeout(15)
            committing = threading.Event()

            def requests():
                try:
                    while data := client.recv(65536):
                        if armed.is_set() and b"COMMIT" in data:
                            committing.set()
                            if not committed:
                                dropped.set()
                                break
                        upstream.sendall(data)
                except OSError:
                    pass
                finally:
                    shutdown()

            request_thread = threading.Thread(target=requests, daemon=True)
            threads.append(request_thread)
            request_thread.start()
            while data := upstream.recv(65536):
                if committing.is_set():
                    # PostgreSQL CommandComplete(COMMIT) is proof the server really committed.
                    if b"COMMIT\x00" in data:
                        dropped.set()
                        break
                    continue
                client.sendall(data)
        except OSError:
            pass
        finally:
            shutdown()
            stopped.set()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        proxy_url = url.set(
            host="127.0.0.1", port=server.getsockname()[1], query={"sslmode": "disable"}
        )
        yield proxy_url.render_as_string(hide_password=False), armed, dropped
    finally:
        shutdown()
        server.close()
        thread.join(timeout=16)
        for item in threads:
            item.join(timeout=2)
        for sock in sockets:
            sock.close()
        assert stopped.is_set()
