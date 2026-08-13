import assert from "node:assert/strict";
import test from "node:test";

import {
  safeUpstreamResponseHeaders,
  validatedControlPlaneBaseUrl,
} from "../lib/weather.ts";

function withEnvironment(environment, callback) {
  const runtime = globalThis;
  const previous = runtime.__WEATHER_ENV__;
  runtime.__WEATHER_ENV__ = environment;
  try {
    return callback();
  } finally {
    runtime.__WEATHER_ENV__ = previous;
  }
}

test("remote control plane requires HTTPS and an allowed DNS hostname", () => {
  withEnvironment(
    {
      CONTROL_PLANE_URL: "https://api.weather.internal",
      CONTROL_PLANE_ALLOWED_HOSTS: "weather.internal",
    },
    () => {
      assert.equal(
        validatedControlPlaneBaseUrl(),
        "https://api.weather.internal",
      );
    },
  );

  for (const value of [
    "http://api.weather.internal",
    "https://user@api.weather.internal",
    "https://api.weather.internal/v1",
    "https://api.weather.internal?mode=test",
    "https://api.weather.internal#fragment",
    "https://127.0.0.1",
    "https://api.weather.internal.example",
  ]) {
    assert.throws(
      () =>
        withEnvironment(
          {
            CONTROL_PLANE_URL: value,
            CONTROL_PLANE_ALLOWED_HOSTS: "weather.internal",
          },
          () => validatedControlPlaneBaseUrl(),
        ),
      /CONTROL_PLANE_URL/,
    );
  }
});

test("local development permits HTTP only for loopback", () => {
  withEnvironment(
    {
      CONTROL_PLANE_MODE: "local-development",
      CONTROL_PLANE_URL: "http://127.0.0.1:8080",
    },
    () => assert.equal(validatedControlPlaneBaseUrl(), "http://127.0.0.1:8080"),
  );
  assert.throws(
    () =>
      withEnvironment(
        {
          CONTROL_PLANE_MODE: "local-development",
          CONTROL_PLANE_URL: "http://weather.internal",
        },
        () => validatedControlPlaneBaseUrl(),
      ),
    /CONTROL_PLANE_URL/,
  );
});

test("upstream response forwarding uses an explicit safe header set", () => {
  const source = new Headers({
    "cache-control": "private, no-store",
    "content-type": "application/json",
    etag: '"abc"',
    "set-cookie": "session=value",
    "x-internal-debug": "internal",
    "x-request-id": "7e190a25-b84f-47ab-b6ac-dac1c6f0d425",
  });
  const safe = safeUpstreamResponseHeaders(source);
  assert.equal(safe.get("content-type"), "application/json");
  assert.equal(safe.get("etag"), '"abc"');
  assert.equal(safe.get("cache-control"), "private, no-store");
  assert.equal(
    safe.get("x-request-id"),
    "7e190a25-b84f-47ab-b6ac-dac1c6f0d425",
  );
  assert.equal(safe.get("set-cookie"), null);
  assert.equal(safe.get("x-internal-debug"), null);
});
