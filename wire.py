"""Shared JSON and protobuf wire codecs and response comparison helpers."""
from __future__ import annotations

import json
import math
from typing import Any, TypeVar

from google.protobuf.message import Message


MessageType = TypeVar("MessageType", bound=Message)


class JsonCodec:
    """Compact UTF-8 JSON codec used by the HTTP/JSON transport."""

    @staticmethod
    def encode(value: Any) -> bytes:
        return json.dumps(
            value, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    @staticmethod
    def decode(payload: bytes) -> Any:
        return json.loads(payload.decode("utf-8"))

    @classmethod
    def encode_line(cls, value: Any) -> bytes:
        return cls.encode(value) + b"\n"


class ProtobufCodec:
    """Protobuf serialization helpers used for wire-size accounting and tests."""

    @staticmethod
    def encode(message: Message) -> bytes:
        return message.SerializeToString()

    @staticmethod
    def decode(payload: bytes, message_type: type[MessageType]) -> MessageType:
        return message_type.FromString(payload)

    @classmethod
    def size(cls, message: Message) -> int:
        return len(cls.encode(message))


def responses_match(
    actual: Any, expected: Any, *, absolute_tolerance: float = 1e-6
) -> bool:
    """Compare JSON-shaped responses, tolerating small floating-point differences."""
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(
                responses_match(
                    actual[key], value, absolute_tolerance=absolute_tolerance
                )
                for key, value in expected.items()
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                responses_match(value, wanted, absolute_tolerance=absolute_tolerance)
                for value, wanted in zip(actual, expected)
            )
        )
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(
            actual, expected, rel_tol=0, abs_tol=absolute_tolerance
        )
    return actual == expected
