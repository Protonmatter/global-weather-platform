import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("the Vite configuration imports a tracked source plugin", async () => {
  const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  assert.match(viteConfig, /from "\.\/sites-vite-plugin"/);
  await access(new URL("../sites-vite-plugin.ts", import.meta.url));
});

test("operational GET and UI paths contain no synthetic seeding", async () => {
  const modelRoute = await readFile(
    new URL("../app/api/model-cycles/route.ts", import.meta.url),
    "utf8",
  );
  const consoleSource = await readFile(
    new URL("../app/components/weather-console.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(modelRoute, /seed|\.insert\(/i);
  assert.doesNotMatch(consoleSource, /sampleObservations|Ingest validation set/);

  const cleanupMigration = await readFile(
    new URL("../drizzle/0003_quarantine_legacy_fixtures.sql", import.meta.url),
    "utf8",
  );
  assert.match(cleanupMigration, /synthetic_validation_fixture/);
  assert.match(cleanupMigration, /DELETE FROM `model_cycles`/);
});

test("legacy observation digests are migrated to a fail-closed sentinel", async () => {
  const migration = await readFile(
    new URL(
      "../drizzle/0002_mark_legacy_observation_digests.sql",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(migration, /SET `content_digest` = 'legacy:unknown'/);
  assert.match(migration, /WHERE `content_digest` = ''/);
});

test("public BFF routes enforce shaping and mutation authentication", async () => {
  const observationsRoute = await readFile(
    new URL("../app/api/v1/observations/route.ts", import.meta.url),
    "utf8",
  );
  const healthRoute = await readFile(
    new URL("../app/api/v1/healthz/route.ts", import.meta.url),
    "utf8",
  );
  const sourceRoute = await readFile(
    new URL("../app/api/v1/source-records/route.ts", import.meta.url),
    "utf8",
  );
  const collectionsRoute = await readFile(
    new URL("../app/api/v1/edr/collections/route.ts", import.meta.url),
    "utf8",
  );
  const auditRoute = await readFile(
    new URL("../app/api/v1/audit/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(observationsRoute, /adaptControlPlaneObservations/);
  assert.match(observationsRoute, /actorFromRequest/);
  assert.match(observationsRoute, /requireServiceAuth: true/);
  assert.match(observationsRoute, /controlPlaneConfigurationProblem/);
  assert.match(observationsRoute, /recordAuditEventBestEffort/);
  assert.match(sourceRoute, /controlPlaneConfigurationProblem/);
  assert.match(sourceRoute, /recordAuditEventBestEffort/);
  assert.match(collectionsRoute, /adaptControlPlaneEdrCollections/);
  assert.match(healthRoute, /adaptControlPlaneHealth/);
  assert.match(auditRoute, /adaptControlPlaneAuditEvents/);
  assert.match(auditRoute, /\/v1\/audit-events/);
  assert.match(auditRoute, /requireServiceAuth: true/);
});

test("production artifacts fail closed while local Vite is explicit", async () => {
  const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  const dockerfile = await readFile(
    new URL("../../../deploy/docker/Dockerfile", import.meta.url),
    "utf8",
  );
  assert.match(viteConfig, /CONTROL_PLANE_MODE:\s*"local-development"/);
  assert.match(viteConfig, /command === "serve"/);
  assert.match(dockerfile, /WEATHER_ENVIRONMENT=production/);
});

test("internal D1 and R2 routes are development-only", async () => {
  const routePaths = [
    "../app/api/observations/route.ts",
    "../app/api/source-records/route.ts",
    "../app/api/model-cycles/route.ts",
    "../app/api/edr/route.ts",
    "../app/api/health/route.ts",
  ];
  for (const path of routePaths) {
    const route = await readFile(new URL(path, import.meta.url), "utf8");
    assert.match(route, /controlPlaneMode\(\) !== "local-development"/);
    assert.match(route, /controlPlaneConfigurationProblem/);
  }
});

test("D1 replay admission uses conflict-aware inserts", async () => {
  const observationRoute = await readFile(
    new URL("../app/api/observations/route.ts", import.meta.url),
    "utf8",
  );
  const sourceRoute = await readFile(
    new URL("../app/api/source-records/route.ts", import.meta.url),
    "utf8",
  );
  for (const route of [observationRoute, sourceRoute]) {
    assert.match(route, /onConflictDoNothing/);
    assert.match(route, /\.returning\(/);
  }
  assert.match(observationRoute, /existing\[0\]\.contentDigest !== contentDigest/);
});
