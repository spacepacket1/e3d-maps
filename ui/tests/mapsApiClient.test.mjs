import test from "node:test";
import assert from "node:assert/strict";

import { buildUrl, createMapsApiClient, emptyPage } from "../src/api/mapsApiClient.js";

test("buildUrl encodes query params without a configured base URL", () => {
  const url = buildUrl("", "/api/maps/signals", {
    signal_type: "capital_migration",
    min_confidence: 0.7,
    limit: 5,
  });

  assert.equal(url, "/api/maps/signals?signal_type=capital_migration&min_confidence=0.7&limit=5");
});

test("getState returns null for a 404 response", async () => {
  const client = createMapsApiClient({
    fetchImpl: async () => ({
      status: 404,
      ok: false,
      statusText: "Not Found",
      json: async () => ({ status: "not_found" }),
    }),
  });

  const state = await client.getState();
  assert.equal(state, null);
});

test("listSignals preserves response payloads", async () => {
  const client = createMapsApiClient({
    fetchImpl: async (url) => {
      assert.match(url, /signal_type=route_hazard/);
      return {
        status: 200,
        ok: true,
        json: async () => ({
          status: "ok",
          signals: [{ id: "navsig_01J" }],
          pagination: { count: 1, has_more: false, limit: 10, offset: 0 },
        }),
      };
    },
  });

  const response = await client.listSignals({ signalType: "route_hazard", limit: 10 });
  assert.deepEqual(response.signals, [{ id: "navsig_01J" }]);
  assert.equal(response.pagination.count, 1);
});

test("listSignals passes all supported filters through query params", async () => {
  let capturedUrl = "";
  const client = createMapsApiClient({
    fetchImpl: async (url) => {
      capturedUrl = url;
      return {
        status: 200,
        ok: true,
        json: async () => ({
          signals: [],
          pagination: { count: 0, has_more: false, limit: 100, offset: 0 },
        }),
      };
    },
  });

  await client.listSignals({
    signalType: "route_hazard",
    minConfidence: 0.75,
    asset: "ETH",
    chain: "ethereum",
    limit: 100,
  });

  assert.match(capturedUrl, /signal_type=route_hazard/);
  assert.match(capturedUrl, /min_confidence=0.75/);
  assert.match(capturedUrl, /asset=ETH/);
  assert.match(capturedUrl, /chain=ethereum/);
  assert.match(capturedUrl, /limit=100/);
});

test("emptyPage provides a stable empty collection shape", () => {
  assert.deepEqual(emptyPage("signals"), {
    signals: [],
    pagination: {
      count: 0,
      has_more: false,
      limit: 0,
      offset: 0,
    },
  });
});

test("getRecommendations passes objective and asset as query params", async () => {
  let capturedUrl = "";
  const client = createMapsApiClient({
    fetchImpl: async (url) => {
      capturedUrl = url;
      return {
        status: 200,
        ok: true,
        json: async () => ({
          generatedAt: "2026-06-12T03:00:00Z",
          objective: "seek_opportunity",
          recommendations: [{ rank: 1, title: "Test", action: "investigate", confidence: 80, risk: 20, score: 76, reasoning: [], supporting_signals: [], supporting_routes: [], story_type: null }],
        }),
      };
    },
  });

  const result = await client.getRecommendations({ objective: "seek_opportunity", asset: "ETH", maxResults: 5 });
  assert.match(capturedUrl, /objective=seek_opportunity/);
  assert.match(capturedUrl, /asset=ETH/);
  assert.match(capturedUrl, /maxResults=5/);
  assert.equal(result.recommendations.length, 1);
  assert.equal(result.recommendations[0].rank, 1);
});

test("getRecommendations returns empty list on failure gracefully", async () => {
  const client = createMapsApiClient({
    fetchImpl: async () => ({
      status: 200,
      ok: true,
      json: async () => null,
    }),
  });

  const result = await client.getRecommendations({});
  assert.deepEqual(result, { generatedAt: null, objective: null, recommendations: [] });
});

test("getFlowGraph returns null for a 404 response", async () => {
  const client = createMapsApiClient({
    fetchImpl: async (url) => {
      assert.equal(url, "/api/maps/graph");
      return {
        status: 404,
        ok: false,
        statusText: "Not Found",
        json: async () => ({ status: "not_found" }),
      };
    },
  });

  const graph = await client.getFlowGraph();
  assert.equal(graph, null);
});

test("getFlowGraph preserves the graph payload when the endpoint is available", async () => {
  const payload = {
    nodes: [{ id: "stablecoins" }],
    edges: [{ origin: "stablecoins", destination: "ETH_DEFI" }],
  };
  const client = createMapsApiClient({
    fetchImpl: async (url) => {
      assert.equal(url, "/api/maps/graph");
      return {
        status: 200,
        ok: true,
        json: async () => payload,
      };
    },
  });

  const graph = await client.getFlowGraph();
  assert.deepEqual(graph, payload);
});
