import assert from "node:assert/strict";
import { createContext, runInContext } from "node:vm";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "sanitize.js"), "utf8");
const context = createContext({ globalThis: {} });
context.globalThis = context;
runInContext(src, context);
const { safeDisplayText } = context.AEA_SAFE_DISPLAY;

test("strips tags and keeps marketplace text inert", () => {
  const out = safeDisplayText("<script>alert(1)</script>hello<img src=x onerror=alert(1)>");
  assert.equal(out.includes("<script>"), false);
  assert.equal(out.includes("<img"), false);
  assert.match(out, /hello/);
});

test("truncates long untrusted content", () => {
  const out = safeDisplayText("A".repeat(500), 40);
  assert.equal(out.length <= 40, true);
});
