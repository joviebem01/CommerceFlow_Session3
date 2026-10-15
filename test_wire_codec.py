"""Tests for the shared JSON/protobuf wire codecs."""
from __future__ import annotations

import unittest

import session3_pb2
from wire import JsonCodec, ProtobufCodec, responses_match


class WireCodecTests(unittest.TestCase):
    def test_json_codec_round_trips_utf8_and_compact_payload(self) -> None:
        value = {"region": "Québec", "rows": [1, 2]}
        payload = JsonCodec.encode(value)
        self.assertEqual(payload, '{"region":"Québec","rows":[1,2]}'.encode("utf-8"))
        self.assertEqual(JsonCodec.decode(payload), value)

    def test_json_codec_encodes_ndjson_lines(self) -> None:
        self.assertEqual(JsonCodec.encode_line({"region": "A"}), b'{"region":"A"}\n')

    def test_protobuf_codec_round_trips_and_reports_serialized_size(self) -> None:
        message = session3_pb2.RegionResponse(
            region="Alabama", transaction_count=7, revenue_total=12.5
        )
        payload = ProtobufCodec.encode(message)
        decoded = ProtobufCodec.decode(payload, session3_pb2.RegionResponse)
        self.assertEqual(decoded, message)
        self.assertEqual(ProtobufCodec.size(message), len(payload))

    def test_responses_match_nested_values_with_float_tolerance(self) -> None:
        expected = {"regions": [{"name": "A", "revenue": 10.0}]}
        actual = {"regions": [{"name": "A", "revenue": 10.0000005}]}
        self.assertTrue(responses_match(actual, expected))
        self.assertFalse(
            responses_match(
                {"regions": [{"name": "A", "revenue": 10.01}]}, expected
            )
        )

    def test_responses_match_rejects_shape_and_type_mismatches(self) -> None:
        self.assertFalse(responses_match({"value": 1, "extra": True}, {"value": 1}))
        self.assertFalse(responses_match({"value": [1]}, {"value": (1,)}))
        self.assertFalse(responses_match({"value": "1"}, {"value": 1}))


if __name__ == "__main__":
    unittest.main()
