import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import test from "node:test";

const TOKEN = "end-to-end-control-plane-token-0001";
const ACTOR = "delivery-e2e@example.test";
const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(appRoot, "../..");

async function allocatePort() {
  const server = createServer();
  await new Promise((resolveListen, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  assert.equal(typeof address, "object");
  const port = address.port;
  await new Promise((resolveClose, reject) =>
    server.close((error) => (error ? reject(error) : resolveClose())),
  );
  return port;
}

async function waitForControlPlane(url, process, output) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) {
      throw new Error(`control plane exited ${process.exitCode}:\n${output.join("")}`);
    }
    try {
      const response = await fetch(`${url}/healthz`);
      if (response.ok) return;
    } catch {
      // Startup races are expected until uvicorn binds its socket.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error(`control plane did not become ready:\n${output.join("")}`);
}

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("e2e", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
}

const executionContext = {
  waitUntil() {},
  passThroughOnException() {},
};

function operatorRequest(path, init = {}) {
  const headers = new Headers(init.headers);
  headers.set("oai-authenticated-user-email", ACTOR);
  return new Request(`https://operator.example${path}`, { ...init, headers });
}

test("built worker traverses the authenticated control plane and authoritative stores", async () => {
  const port = await allocatePort();
  const controlPlaneUrl = `http://127.0.0.1:${port}`;
  const dataDirectory = await mkdtemp(resolve(tmpdir(), "weather-e2e-"));
  const output = [];
  const python = process.env.PYTHON_BIN || resolve(repositoryRoot, ".venv/bin/python");
  const controlPlane = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "weather_platform.api.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--log-level",
      "warning",
    ],
    {
      cwd: repositoryRoot,
      env: {
        ...process.env,
        PYTHONPATH: resolve(repositoryRoot, "src"),
        WEATHER_ENVIRONMENT: "production",
        WEATHER_DATA_DIR: dataDirectory,
        WEATHER_CONTROL_PLANE_TOKEN: TOKEN,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  controlPlane.stdout.on("data", (chunk) => output.push(chunk.toString()));
  controlPlane.stderr.on("data", (chunk) => output.push(chunk.toString()));

  try {
    await waitForControlPlane(controlPlaneUrl, controlPlane, output);
    const worker = await loadWorker();
    const environment = {
      ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
      CONTROL_PLANE_MODE: "local-development",
      CONTROL_PLANE_URL: controlPlaneUrl,
      CONTROL_PLANE_TOKEN: TOKEN,
    };

    const health = await worker.fetch(
      operatorRequest("/api/v1/healthz"),
      environment,
      executionContext,
    );
    assert.equal(health.status, 200);
    assert.equal((await health.json()).status, "ok");

    const sourceBytes = new TextEncoder().encode("deterministic end-to-end source evidence");
    const retained = await worker.fetch(
      operatorRequest("/api/v1/source-records", {
        method: "POST",
        headers: { "content-type": "application/octet-stream" },
        body: sourceBytes,
      }),
      environment,
      executionContext,
    );
    assert.equal(retained.status, 201);
    const retainedBody = await retained.json();
    assert.match(retainedBody.source_record_digest, /^sha256:[a-f0-9]{64}$/);

    const admitted = await worker.fetch(
      operatorRequest("/api/v1/observations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          phenomenon: "air_temperature",
          value: 281.4,
          unit: "K",
          uncertainty: 0.2,
          longitude: -73.9857,
          latitude: 40.7484,
          observedAt: "2026-08-14T12:00:00Z",
          qualityDisposition: "accept",
          qualityFlags: [],
          sourceId: "delivery-e2e",
          sourceDigest: retainedBody.source_record_digest,
          decoderVersion: "delivery-e2e/1.0.0",
          recordIndex: 0,
        }),
      }),
      environment,
      executionContext,
    );
    assert.equal(admitted.status, 202);
    assert.equal((await admitted.json()).status, "accepted");

    const observations = await worker.fetch(
      operatorRequest("/api/v1/observations?phenomenon=air_temperature"),
      environment,
      executionContext,
    );
    assert.equal(observations.status, 200);
    const observationBody = await observations.json();
    assert.equal(observationBody.observations.length, 1);
    assert.equal(observationBody.observations[0].sourceDigest, retainedBody.source_record_digest);

    const audit = await worker.fetch(
      operatorRequest("/api/v1/audit"),
      environment,
      executionContext,
    );
    assert.equal(audit.status, 200);
    const events = (await audit.json()).events;
    assert.equal(events.length, 4);
    assert.deepEqual(
      events.map((event) => `${event.action}:${event.result}`),
      [
        "observation.admitted:succeeded",
        "observation.admitted:attempted",
        "source_record.retained:succeeded",
        "source_record.retained:attempted",
      ],
    );
    assert.ok(events.every((event) => event.actor === ACTOR));
  } finally {
    controlPlane.kill("SIGTERM");
    await Promise.race([
      new Promise((resolveExit) => controlPlane.once("exit", resolveExit)),
      new Promise((resolveTimeout) => setTimeout(resolveTimeout, 5_000)),
    ]);
    if (controlPlane.exitCode === null) controlPlane.kill("SIGKILL");
    await rm(dataDirectory, { recursive: true, force: true });
  }
});
