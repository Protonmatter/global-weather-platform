import assert from "node:assert/strict";
import test from "node:test";

import {
  angularDistanceDegrees,
  deterministicObservationId,
  isPhenomenon,
  parseDatetimeInterval,
  parseWktPoint,
  sha256Text,
} from "../lib/weather.ts";

test("observation identifiers are deterministic UUIDv5-shaped values", async () => {
  const first = await deterministicObservationId("sha256:abc", "decoder-1", 0);
  const replay = await deterministicObservationId("sha256:abc", "decoder-1", 0);
  const nextRecord = await deterministicObservationId(
    "sha256:abc",
    "decoder-1",
    1,
  );

  assert.equal(first, replay);
  assert.notEqual(first, nextRecord);
  assert.match(
    first,
    /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});

test("text digests are SHA-256-prefixed and stable", async () => {
  assert.equal(
    await sha256Text("weather"),
    "sha256:e5e72beb4e3c6926d3dc9e3e2ef7833ba50cd919c2460a782b244fd071e920de",
  );
});

test("WKT parsing accepts boundary coordinates and rejects invalid input", () => {
  assert.deepEqual(parseWktPoint(" POINT ( -180 90 ) "), {
    longitude: -180,
    latitude: 90,
  });
  assert.throws(() => parseWktPoint("POINT(181 0)"), /longitude/);
  assert.throws(() => parseWktPoint("POINT(0 -91)"), /latitude/);
  assert.throws(() => parseWktPoint("LINESTRING(0 0, 1 1)"), /WKT POINT/);
});

test("datetime parsing preserves instants and open intervals", () => {
  assert.deepEqual(parseDatetimeInterval("2026-07-25T00:00:00Z"), {
    start: "2026-07-25T00:00:00.000Z",
    end: "2026-07-25T00:00:00.000Z",
  });
  assert.deepEqual(
    parseDatetimeInterval("../2026-07-25T00:00:00Z"),
    {
      start: null,
      end: "2026-07-25T00:00:00.000Z",
    },
  );
  assert.throws(
    () =>
      parseDatetimeInterval(
        "2026-07-26T00:00:00Z/2026-07-25T00:00:00Z",
      ),
    /must not precede/,
  );
  assert.throws(() => parseDatetimeInterval("not-a-date"), /ISO 8601/);
});

test("angular distance uses the shortest antimeridian delta", () => {
  assert.equal(angularDistanceDegrees(179, 10, -179, 10), 2);
});

test("phenomenon names use bounded canonical identifiers", () => {
  assert.equal(isPhenomenon("air_temperature"), true);
  assert.equal(isPhenomenon("AirTemperature"), false);
  assert.equal(isPhenomenon(`a${"b".repeat(80)}`), false);
});
