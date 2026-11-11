"""Data lake de viabilidad de data centers (hackathon)."""

__version__ = "0.1.0"

# Corporate networks with TLS inspection re-sign HTTPS traffic with their own root CA,
# which lives in the Windows certificate store but not in certifi. truststore makes
# requests/urllib (and therefore cdsapi and ObsPy) trust the OS store.
try:
    import truststore as _truststore

    _truststore.inject_into_ssl()
except Exception:  # optional dependency
    pass
