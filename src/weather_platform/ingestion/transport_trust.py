"""Acquisition transport integrity verification (DATA-004).

Acquisition workers present the TLS issuer chain they observed for a source and
the upstream-published checksum of the bytes they fetched. This module verifies
both against a per-source policy and fails closed on anything unexpected — an
unpinned issuer (an interception proxy), an unauthenticated scheme, or a
checksum mismatch. The live MQTT/HTTPS wiring that supplies the observed chain
lives in the acquisition trust zone and is deployment-specific; this is the
verification core it calls, exercised here with injected values.
"""

import hashlib
import hmac

from pydantic import BaseModel, ConfigDict, Field

_CHECKSUM_ALGORITHMS = {"sha256", "sha384", "sha512"}


class TransportVerificationError(ValueError):
    """Raised when observed transport does not satisfy the source trust policy."""


class SourceTrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    # Acceptable issuer identifiers (CA common names or SPKI fingerprints). Every
    # issuer in the observed chain must appear here.
    pinned_issuers: list[str] = Field(min_length=1)
    require_https: bool = True


class TransportAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    scheme: str
    observed_issuers: list[str]
    verified: bool


def verify_transport(
    policy: SourceTrustPolicy,
    *,
    scheme: str,
    observed_issuers: list[str],
) -> TransportAttestation:
    """Verify an observed transport chain against the source policy, failing closed.

    Returns an attestation recording the observed chain so provenance can
    distinguish independently verified transport from unverified transport.
    """
    if policy.require_https and scheme != "https":
        raise TransportVerificationError(
            f"source {policy.source_id} refuses unauthenticated transport ({scheme})"
        )
    if not observed_issuers:
        raise TransportVerificationError(f"source {policy.source_id} presented no issuer chain")
    allowed = set(policy.pinned_issuers)
    unexpected = sorted({issuer for issuer in observed_issuers if issuer not in allowed})
    if unexpected:
        # An issuer outside the pin is an interception indicator; do not proceed.
        raise TransportVerificationError(
            f"source {policy.source_id} presented unpinned issuer(s): {unexpected}"
        )
    return TransportAttestation(
        source_id=policy.source_id,
        scheme=scheme,
        observed_issuers=observed_issuers,
        verified=True,
    )


def verify_upstream_checksum(payload: bytes, *, algorithm: str, expected_hex: str) -> None:
    """Verify fetched bytes against an upstream-published checksum before retention."""
    if algorithm not in _CHECKSUM_ALGORITHMS:
        raise TransportVerificationError(f"unsupported checksum algorithm {algorithm}")
    computed = hashlib.new(algorithm, payload).hexdigest()
    if not hmac.compare_digest(computed, expected_hex.strip().lower()):
        raise TransportVerificationError("upstream checksum does not match fetched bytes")
