import test from "node:test";
import assert from "node:assert/strict";

import { truncateAnswer } from "../src/utils/truncateAnswer.js";

test("truncateAnswer returns an em dash for empty values", () => {
  assert.equal(truncateAnswer(""), "—");
  assert.equal(truncateAnswer(null), "—");
});

test("truncateAnswer leaves short answers unchanged", () => {
  const answer = "Short signal summary.";

  assert.equal(truncateAnswer(answer), answer);
});

test("truncateAnswer trims long answers to 120 characters with ellipsis", () => {
  const answer = "A".repeat(121);
  const truncated = truncateAnswer(answer);

  assert.equal(truncated.length, 121);
  assert.equal(truncated, `${"A".repeat(120)}…`);
});
