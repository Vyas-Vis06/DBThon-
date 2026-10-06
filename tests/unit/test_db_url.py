from sqlalchemy.engine import make_url

from zeroentry.db import url_for


def test_url_for_reaches_tcp_and_unix_socket_servers():
    """pgserver hands out host:port on Windows and a socket directory on Linux/macOS (CI caught the second case)."""
    tcp = make_url(url_for("postgresql://postgres:@localhost:5433/postgres", "ze", "ze_app", "p@ss/word"))
    assert (tcp.database, tcp.username, tcp.password) == ("ze", "ze_app", "p@ss/word")
    assert dict(tcp.query) == {"host": "localhost", "port": "5433"}
    sock = make_url(url_for("postgresql://postgres:@/postgres?host=/tmp/pg%20dir", "ze"))
    assert sock.host is None and dict(sock.query) == {"host": "/tmp/pg dir"} and sock.database == "ze"
