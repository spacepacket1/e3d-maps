import test from "node:test";
import assert from "node:assert/strict";

import { RECOMMENDATION_ACTION_CLASSES } from "../src/utils/recommendationActionClasses.js";

test("recommendation action classes keep dashboard and recommendations badges aligned", () => {
  assert.equal(RECOMMENDATION_ACTION_CLASSES.increase_exposure, "badge-positive");
  assert.equal(RECOMMENDATION_ACTION_CLASSES.reduce_exposure, "badge-warning");
  assert.equal(RECOMMENDATION_ACTION_CLASSES.investigate, "badge-accent");
  assert.equal(RECOMMENDATION_ACTION_CLASSES.monitor, "badge-neutral");
});
