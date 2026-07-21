# ADR-0001: Python control plane

**Status:** Accepted

Python 3.12 is used for initial API, ingestion orchestration, provenance, and verification services. Numerical forecast cores are explicitly outside this language decision.

Reasons:

- strong Earth-science ecosystem;
- typed API and schema tooling;
- direct compatibility with xarray, NumPy, JAX, PyTorch, ecCodes, and scientific verification libraries;
- lower cost for the first vertical slice.
