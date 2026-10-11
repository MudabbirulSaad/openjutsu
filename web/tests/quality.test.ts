import { expect, test } from "vitest";
import {
  orderedFindings,
  type QualityFinding,
} from "../src/PreparationQuality";

test("confirmed defects and required decisions precede warnings and accepted evidence", () => {
  const findings = [
    { id: "pass", status: "PASS", start: 0 },
    { id: "warning", status: "WARNING", start: 2 },
    { id: "blocked", status: "BLOCKED", start: 260 },
    { id: "reviewed", status: "REVIEWED", start: 160 },
    { id: "earlier", status: "BLOCKED", start: 230 },
  ] as QualityFinding[];
  expect(orderedFindings(findings).map((f) => f.id)).toEqual([
    "earlier",
    "blocked",
    "warning",
    "reviewed",
    "pass",
  ]);
  expect(findings[0].id).toBe("pass");
});
