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
