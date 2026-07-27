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
  assert.match(observationsRoute, /adaptControlPlaneObservations/);
  assert.match(observationsRoute, /actorFromRequest/);
  assert.match(observationsRoute, /requireServiceAuth: true/);
  assert.match(healthRoute, /adaptControlPlaneHealth/);
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
