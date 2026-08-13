import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import chain

_MAGIC = b"WVEC"
_VERSION = 1
_FLAGS = 0
_QUANTIZATION_LIMIT = 32767
_HEADER = struct.Struct(">4sBBHHdddd")
_SAMPLE = struct.Struct(">hh")


class VectorTileError(ValueError):
    """Raised when a vector tile cannot be encoded or trusted."""


@dataclass(frozen=True, slots=True)
class VectorTileHeader:
    version: int
    width: int
    height: int
    scale_u: float
    offset_u: float
    scale_v: float
    offset_v: float


def _quantize(values: Sequence[float]) -> tuple[float, float, list[int]]:
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return 1.0, minimum, [0] * len(values)

    # Dividing the endpoints before combining them avoids overflowing on
    # finite ranges such as [-1e308, 1e308] or [1e308, 1.7e308].
    offset = minimum / 2.0 + maximum / 2.0
    half_range = maximum / 2.0 - minimum / 2.0
    scale = half_range / _QUANTIZATION_LIMIT
    if not math.isfinite(offset) or not math.isfinite(scale) or scale <= 0:
        raise VectorTileError("component range cannot be represented with finite tile metadata")

    try:
        encoded = [
            max(
                -_QUANTIZATION_LIMIT,
                min(_QUANTIZATION_LIMIT, round((value - offset) / scale)),
            )
            for value in values
        ]
    except (OverflowError, ValueError) as exc:
        raise VectorTileError("component range cannot be quantized safely") from exc

    if any(not math.isfinite(value * scale + offset) for value in encoded):
        raise VectorTileError("quantized components would decode to non-finite values")
    return scale, offset, encoded


def encode_vector_tile(
    u_components: Sequence[float],
    v_components: Sequence[float],
    *,
    width: int,
    height: int,
) -> bytes:
    """Encode interleaved U/V components as a versioned signed-16-bit tile."""

    if width <= 0 or height <= 0:
        raise VectorTileError("tile dimensions must be positive")
    if width > 65535 or height > 65535:
        raise VectorTileError("tile dimensions exceed the wire format limit")
    if len(u_components) != len(v_components):
        raise VectorTileError("U and V components must have the same length")

    expected_count = width * height
    if len(u_components) != expected_count:
        raise VectorTileError("component sample count does not match tile dimensions")
    if any(not math.isfinite(value) for value in chain(u_components, v_components)):
        raise VectorTileError("vector components must be finite")

    scale_u, offset_u, encoded_u = _quantize(u_components)
    scale_v, offset_v, encoded_v = _quantize(v_components)
    header = _HEADER.pack(
        _MAGIC,
        _VERSION,
        _FLAGS,
        width,
        height,
        scale_u,
        offset_u,
        scale_v,
        offset_v,
    )
    body = bytearray(expected_count * _SAMPLE.size)
    for index, (encoded_u_value, encoded_v_value) in enumerate(
        zip(encoded_u, encoded_v, strict=True)
    ):
        _SAMPLE.pack_into(body, index * _SAMPLE.size, encoded_u_value, encoded_v_value)
    return header + bytes(body)


def decode_vector_tile(payload: bytes) -> tuple[VectorTileHeader, list[float], list[float]]:
    """Decode and strictly validate a binary U/V vector tile."""

    if len(payload) < _HEADER.size:
        raise VectorTileError("vector tile length is shorter than its header")

    magic, version, flags, width, height, scale_u, offset_u, scale_v, offset_v = (
        _HEADER.unpack_from(payload)
    )
    if magic != _MAGIC:
        raise VectorTileError("invalid vector tile magic")
    if version != _VERSION:
        raise VectorTileError(f"unsupported vector tile version {version}")
    if flags != _FLAGS:
        raise VectorTileError("unsupported vector tile flags")
    if width <= 0 or height <= 0:
        raise VectorTileError("vector tile dimensions must be positive")
    if not all(math.isfinite(value) for value in (scale_u, offset_u, scale_v, offset_v)):
        raise VectorTileError("vector tile scale and offset values must be finite")
    if scale_u <= 0 or scale_v <= 0:
        raise VectorTileError("vector tile scales must be positive")

    sample_count = width * height
    expected_length = _HEADER.size + sample_count * _SAMPLE.size
    if len(payload) != expected_length:
        raise VectorTileError(
            f"vector tile length {len(payload)} does not match expected {expected_length}"
        )

    decoded_u: list[float] = []
    decoded_v: list[float] = []
    for index in range(sample_count):
        encoded_u, encoded_v = _SAMPLE.unpack_from(payload, _HEADER.size + index * _SAMPLE.size)
        u_value = encoded_u * scale_u + offset_u
        v_value = encoded_v * scale_v + offset_v
        if not math.isfinite(u_value) or not math.isfinite(v_value):
            raise VectorTileError("vector tile samples decode to non-finite values")
        decoded_u.append(u_value)
        decoded_v.append(v_value)

    header = VectorTileHeader(
        version=version,
        width=width,
        height=height,
        scale_u=scale_u,
        offset_u=offset_u,
        scale_v=scale_v,
        offset_v=offset_v,
    )
    return header, decoded_u, decoded_v
