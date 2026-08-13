import assert from "node:assert/strict";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

async function loadWorker() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
}

const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};

const executionContext = {
  waitUntil() {},
  passThroughOnException() {},
};

test("redirects unauthenticated HTML requests to ChatGPT sign-in", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
      redirect: "manual",
    }),
    environment,
    executionContext,
  );

  assert.equal(response.status, 307);
  assert.equal(
    new URL(response.headers.get("location"), "http://localhost").pathname,
    "/signin-with-chatgpt",
  );
});

test("renders development preview metadata for a verified workspace user", async () => {
  const worker = await loadWorker();
  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: {
        accept: "text/html",
        "oai-authenticated-user-email": "operator@example.test",
        "oai-authenticated-user-full-name": "Development%20Operator",
        "oai-authenticated-user-full-name-encoding": "percent-encoded-utf-8",
      },
    }),
    environment,
    executionContext,
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  assert.match(await response.text(), developmentPreviewMeta);
});
