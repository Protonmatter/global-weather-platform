import math

import pytest

from weather_platform.serving.vector_tiles import (
    VectorTileError,
    decode_vector_tile,
    encode_vector_tile,
)


def test_round_trip_preserves_shape_and_values_with_bounded_error() -> None:
    u = [-12.5, -1.0, 0.0, 3.5, 18.0, 7.25]
    v = [4.0, -8.5, 0.0, 2.25, 9.5, -3.0]
    payload = encode_vector_tile(u, v, width=3, height=2)
    header, decoded_u, decoded_v = decode_vector_tile(payload)

    assert header.version == 1
    assert (header.width, header.height) == (3, 2)
    assert decoded_u == pytest.approx(u, abs=header.scale_u / 2 + 1e-12)
    assert decoded_v == pytest.approx(v, abs=header.scale_v / 2 + 1e-12)


def test_encoding_is_deterministic() -> None:
    u = [1.0, 2.0, 3.0, 4.0]
    v = [-1.0, -2.0, -3.0, -4.0]
    assert encode_vector_tile(u, v, width=2, height=2) == encode_vector_tile(
        u, v, width=2, height=2
    )


def test_constant_fields_round_trip_without_division_by_zero() -> None:
    payload = encode_vector_tile([5.5] * 4, [-2.0] * 4, width=2, height=2)
    header, u, v = decode_vector_tile(payload)
    assert header.scale_u > 0
    assert header.scale_v > 0
    assert u == pytest.approx([5.5] * 4)
    assert v == pytest.approx([-2.0] * 4)


def test_shape_mismatch_and_invalid_dimensions_are_rejected() -> None:
    with pytest.raises(VectorTileError, match="sample count"):
        encode_vector_tile([1.0], [1.0], width=2, height=1)
    with pytest.raises(VectorTileError, match="positive"):
        encode_vector_tile([], [], width=0, height=0)
    with pytest.raises(VectorTileError, match="same length"):
        encode_vector_tile([1.0, 2.0], [1.0], width=1, height=2)


def test_non_finite_components_are_rejected() -> None:
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(VectorTileError, match="finite"):
            encode_vector_tile([value], [0.0], width=1, height=1)


def test_large_finite_ranges_encode_without_overflow() -> None:
    expected_u = [-1.0e308, 1.0e308]
    expected_v = [1.0e308, 1.7e308]
    payload = encode_vector_tile(expected_u, expected_v, width=2, height=1)
    header, u, v = decode_vector_tile(payload)

    assert all(math.isfinite(value) for value in (header.scale_u, header.offset_u))
    assert all(math.isfinite(value) for value in (header.scale_v, header.offset_v))
    assert u == pytest.approx(expected_u, abs=header.scale_u / 2)
    assert v == pytest.approx(expected_v, abs=header.scale_v / 2)


def test_decoder_rejects_wrong_magic_version_or_truncation() -> None:
    payload = bytearray(encode_vector_tile([1.0], [2.0], width=1, height=1))

    wrong_magic = bytearray(payload)
    wrong_magic[:4] = b"NOPE"
    with pytest.raises(VectorTileError, match="magic"):
        decode_vector_tile(bytes(wrong_magic))

    wrong_version = bytearray(payload)
    wrong_version[4] = 99
    with pytest.raises(VectorTileError, match="version"):
        decode_vector_tile(bytes(wrong_version))

    with pytest.raises(VectorTileError, match="length"):
        decode_vector_tile(bytes(payload[:-1]))


def test_cardinal_vector_signs_survive_wire_format() -> None:
    payload = encode_vector_tile(
        [0.0, -10.0, 0.0, 10.0],
        [-10.0, 0.0, 10.0, 0.0],
        width=4,
        height=1,
    )
    _, u, v = decode_vector_tile(payload)
    assert v[0] < 0
    assert u[1] < 0
    assert v[2] > 0
    assert u[3] > 0
