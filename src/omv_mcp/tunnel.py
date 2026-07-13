"""Lazy SSH tunnel to the NAS's Portainer (Mode B only).

Portainer listens on the NAS's localhost:9000 over plain HTTP. Rather than
requiring that port to be reachable (and sending the API key in cleartext
across the network), we forward a local ephemeral port through the same
persistent SSH connection ``ssh_remote`` already holds — the paramiko
equivalent of ``ssh -L``. Started on first use; every accepted local
connection becomes one ``direct-tcpip`` channel.
"""

import logging
import socketserver
import threading

from .ssh_remote import get_client

log = logging.getLogger(__name__)

# Portainer as seen FROM the NAS. Alternate setups use the PORTAINER_URL
# escape hatch instead of tunnelling.
_DEST = ("127.0.0.1", 9000)

_lock = threading.Lock()
_server: socketserver.ThreadingTCPServer | None = None
_port: int | None = None


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        try:
            chan = get_client().get_transport().open_channel(
                "direct-tcpip", _DEST, sock.getsockname()
            )
        except Exception as e:
            log.warning("Portainer tunnel channel failed: %s", e)
            return

        def sock_to_chan():
            try:
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    chan.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    chan.shutdown_write()
                except Exception:
                    pass

        threading.Thread(target=sock_to_chan, daemon=True).start()
        try:
            while True:
                data = chan.recv(65536)
                if not data:
                    break
                sock.sendall(data)
        except OSError:
            pass
        finally:
            try:
                chan.close()
            except Exception:
                pass


def tunnel_url() -> str:
    """Local base URL for Portainer, starting the forwarder on first call."""
    global _server, _port
    with _lock:
        if _server is None:
            srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
            srv.daemon_threads = True
            threading.Thread(
                target=srv.serve_forever, name="portainer-tunnel", daemon=True
            ).start()
            _server, _port = srv, srv.server_address[1]
            log.info("Portainer tunnel listening on 127.0.0.1:%d -> NAS %s:%d",
                     _port, *_DEST)
    return f"http://127.0.0.1:{_port}/api"
