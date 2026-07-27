import assert from "node:assert/strict";
import test from "node:test";

import {
  adaptControlPlaneHealth,
  adaptControlPlaneModelCycles,
  adaptControlPlaneObservations,
  angularDistanceDegrees,
  deterministicObservationId,
  isPhenomenon,
  longitudeRanges,
  normalizeObservationInput,
  parseDatetimeInterval,
  parseWktPoint,
  proxyToControlPlane,
  readBoundedRequestBody,
  RequestBodyError,
  sha256Text,
  toControlPlaneObservation,
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
  assert.equal(first, "8766734e-7a48-5131-8e8b-d545176a8c10");
  assert.equal(nextRecord, "761bee8a-c684-5ca5-a3bb-592cb39a83c2");
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
  assert.ok(Math.abs(angularDistanceDegrees(179, 10, -179, 10) - 1.9696) < 0.001);
  assert.ok(Math.abs(angularDistanceDegrees(0, 89, 90, 89) - 1.414) < 0.01);
});

test("spatial bounding ranges conservatively cover polar and wrapped queries", () => {
  assert.deepEqual(longitudeRanges(0, 89.8, 0.5), [[-180, 180]]);
  assert.deepEqual(longitudeRanges(179.9, 0, 0.5), [
    [179.4, 180],
    [-180, -179.6],
  ]);
});

test("phenomenon names use bounded canonical identifiers", () => {
  assert.equal(isPhenomenon("air_temperature"), true);
  assert.equal(isPhenomenon("AirTemperature"), false);
  assert.equal(isPhenomenon(`a${"b".repeat(80)}`), false);
});

const validObservation = {
  phenomenon: "air_temperature",
  value: 273.15,
  unit: "K",
  uncertainty: 0.2,
  longitude: 10,
  latitude: 20,
  observedAt: "2026-07-25T00:00:00Z",
  qualityDisposition: "accept",
  qualityFlags: [],
  sourceId: "test-source",
  sourceDigest: `sha256:${"a".repeat(64)}`,
  decoderVersion: "test-decoder/1",
  recordIndex: 0,
};

test("observation validation rejects canonical contract drift", () => {
  assert.throws(
    () => normalizeObservationInput({ ...validObservation, uncertainty: -1 }),
    /non-negative/,
  );
  assert.throws(
    () => normalizeObservationInput({ ...validObservation, observedAt: "2026-07-25" }),
    /timezone/,
  );
  assert.throws(
    () => normalizeObservationInput({ ...validObservation, qualityFlags: ["ok", 1] }),
    /array of strings/,
  );
  assert.throws(
    () => normalizeObservationInput({ ...validObservation, qualityFlags: ["x", "x"] }),
    /duplicates/,
  );
});

test("canonical mutation payload uses the normalized FastAPI contract", async () => {
  const normalized = normalizeObservationInput(validObservation);
  const id = await deterministicObservationId(
    normalized.sourceDigest,
    normalized.decoderVersion,
    normalized.recordIndex,
  );
  const canonical = toControlPlaneObservation(
    normalized,
    id,
    "2026-07-25T00:01:00.000Z",
  );
  assert.equal(canonical.observation_id, id);
  assert.deepEqual(canonical.geometry.coordinates, [10, 20]);
  assert.equal(canonical.provenance.source_record_digest, normalized.sourceDigest);
  assert.equal(canonical.observation_time, "2026-07-25T00:00:00.000Z");
});

test("streaming body limit rejects an understated content length", async () => {
  const request = new Request("https://site.example/api/v1/source-records", {
    method: "POST",
    headers: { "content-length": "1" },
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("1234"));
        controller.enqueue(new TextEncoder().encode("56789"));
        controller.close();
      },
    }),
    duplex: "half",
  });
  await assert.rejects(
    () => readBoundedRequestBody(request, 8),
    (error) => error instanceof RequestBodyError && error.status === 413,
  );
});

test("control-plane proxy allowlists headers and replaces identity", async () => {
  const runtime = globalThis;
  const originalEnvironment = runtime.__WEATHER_ENV__;
  const originalFetch = globalThis.fetch;
  let captured;
  runtime.__WEATHER_ENV__ = {
    CONTROL_PLANE_URL: "https://control.example",
    CONTROL_PLANE_TOKEN: "s".repeat(32),
  };
  globalThis.fetch = async (url, init) => {
    captured = { url: String(url), init };
    return Response.json({ status: "ok" });
  };
  try {
    const request = new Request("https://site.example/api/v1/observations", {
      method: "POST",
      headers: {
        authorization: "Bearer attacker",
        cookie: "secret=value",
        "content-type": "application/json",
        "x-weather-actor": "spoofed@example.invalid",
      },
      body: "{}",
    });
    await proxyToControlPlane(request, "/v1/observations", {
      actor: "verified@example.invalid",
      body: "{}",
      requireServiceAuth: true,
    });
    const headers = new Headers(captured.init.headers);
    assert.equal(captured.url, "https://control.example/v1/observations");
    assert.equal(headers.get("authorization"), `Bearer ${"s".repeat(32)}`);
    assert.equal(headers.get("x-weather-actor"), "verified@example.invalid");
    assert.equal(headers.get("cookie"), null);
  } finally {
    globalThis.fetch = originalFetch;
    runtime.__WEATHER_ENV__ = originalEnvironment;
  }
});

test("control-plane mutations reject short service credentials", async () => {
  const runtime = globalThis;
  const originalEnvironment = runtime.__WEATHER_ENV__;
  runtime.__WEATHER_ENV__ = {
    CONTROL_PLANE_URL: "https://control.example",
    CONTROL_PLANE_TOKEN: "short",
  };
  try {
    await assert.rejects(
      () =>
        proxyToControlPlane(
          new Request("https://site.example/api/v1/observations", {
            method: "POST",
            body: "{}",
          }),
          "/v1/observations",
          { body: "{}", requireServiceAuth: true },
        ),
      /CONTROL_PLANE_TOKEN/,
    );
  } finally {
    runtime.__WEATHER_ENV__ = originalEnvironment;
  }
});

test("authoritative responses are normalized to console DTOs", () => {
  const sourceDigest = `sha256:${"b".repeat(64)}`;
  const observations = adaptControlPlaneObservations([
    {
      observation_id: "8766734e-7a48-5131-8e8b-d545176a8c10",
      phenomenon: "air_temperature",
      value: 273.15,
      unit: "K",
      uncertainty: 0.2,
      geometry: { type: "Point", coordinates: [10, 20] },
      observation_time: "2026-07-25T00:00:00Z",
      ingestion_time: "2026-07-25T00:01:00Z",
      quality_disposition: "accept",
      quality_flags: [],
      provenance: {
        source_id: "test",
        source_record_digest: sourceDigest,
        decoder_version: "decoder/1",
      },
    },
  ]);
  assert.equal(observations.observations[0].sourceDigest, sourceDigest);
  assert.equal(observations.observations[0].longitude, 10);

  const cycles = adaptControlPlaneModelCycles([
    {
      id: "cycle-id",
      model_id: "gfs",
      model_version: "1",
      guidance_origin: "imported",
      initialized_at: "2026-07-25T00:00:00Z",
      source_revision: "rev",
      completeness: "partial",
      available_field_count: 1,
      expected_field_count: 2,
      updated_at: "2026-07-25T00:00:00Z",
    },
  ]);
  assert.equal(cycles.cycles[0].availableFieldCount, 1);

  const health = adaptControlPlaneHealth({
    status: "ok",
    version: "0.1.0",
    telemetry_enabled: false,
    external_egress_enabled: false,
  });
  assert.equal(health.control_plane_mode, "remote-authoritative");
  assert.equal(health.persistence.canonical_observations, null);
});
