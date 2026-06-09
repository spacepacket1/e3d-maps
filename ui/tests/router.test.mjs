import test from "node:test";
import assert from "node:assert/strict";

import { matchRoute, normalizePathname, shouldHandleNavigation } from "../src/router.js";

test("normalizePathname collapses trailing slashes", () => {
  assert.equal(normalizePathname("/signals/"), "/signals");
  assert.equal(normalizePathname("/"), "/");
});

test("matchRoute resolves dynamic signal detail paths", () => {
  const route = matchRoute("/signals/navsig_01J");
  assert.equal(route.routeId, "signal-detail");
  assert.deepEqual(route.params, { id: "navsig_01J" });
});

test("matchRoute falls back to not-found for unknown pages", () => {
  const route = matchRoute("/does-not-exist");
  assert.equal(route.routeId, "not-found");
});

test("shouldHandleNavigation only intercepts plain left-click internal links", () => {
  assert.equal(
    shouldHandleNavigation(
      { defaultPrevented: false, button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false },
      "/signals"
    ),
    true
  );
  assert.equal(
    shouldHandleNavigation(
      { defaultPrevented: false, button: 1, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false },
      "/signals"
    ),
    false
  );
});
