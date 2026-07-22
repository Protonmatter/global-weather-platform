import hashlib

import pytest

from weather_platform.ingestion.transport_trust import (
    SourceTrustPolicy,
    TransportVerificationError,
    verify_transport,
    verify_upstream_checksum,
)

POLICY = SourceTrustPolicy(
    source_id="de-dwd",
    pinned_issuers=["DWD Root CA", "DWD Issuing CA"],
)


def test_pinned_chain_is_verified() -> None:
    attestation = verify_transport(
        POLICY, scheme="https", observed_issuers=["DWD Issuing CA", "DWD Root CA"]
    )
    assert attestation.verified is True
    assert attestation.observed_issuers == ["DWD Issuing CA", "DWD Root CA"]


def test_interception_proxy_issuer_fails_closed() -> None:
    with pytest.raises(TransportVerificationError, match="unpinned issuer"):
        verify_transport(
            POLICY,
            scheme="https",
            observed_issuers=["DWD Issuing CA", "CCR Upstream Proxy CA (staging)"],
        )


def test_unauthenticated_scheme_is_rejected() -> None:
    with pytest.raises(TransportVerificationError, match="unauthenticated"):
        verify_transport(POLICY, scheme="http", observed_issuers=["DWD Root CA"])


def test_empty_chain_is_rejected() -> None:
    with pytest.raises(TransportVerificationError, match="no issuer chain"):
        verify_transport(POLICY, scheme="https", observed_issuers=[])


def test_upstream_checksum_match_and_mismatch() -> None:
    payload = b"grib-message-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    verify_upstream_checksum(payload, algorithm="sha256", expected_hex=digest.upper())
    with pytest.raises(TransportVerificationError, match="does not match"):
        verify_upstream_checksum(payload, algorithm="sha256", expected_hex="00" * 32)
    with pytest.raises(TransportVerificationError, match="unsupported"):
        verify_upstream_checksum(payload, algorithm="md5", expected_hex=digest)
