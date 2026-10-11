import { describe, expect, it } from "vitest";
import { normalizedPoint } from "../src/Viewer";
import { timecode } from "../src/api";
describe("annotation coordinates and frame timing", () => {
  it("maps the contained image rather than its letterbox", () => {
    const rect = { left: 20, top: 10, width: 800, height: 600 };
    expect(normalizedPoint(420, 310, rect, 1920, 1080)).toEqual({
      x: 0.5,
      y: 0.5,
      include: true,
    });
    expect(normalizedPoint(420, 20, rect, 1920, 1080)).toBeNull();
    expect(normalizedPoint(20, 85, rect, 1920, 1080)).toEqual({
      x: 0,
      y: 0,
      include: true,
    });
  });
  it("maps portrait images independently of responsive scale", () => {
    expect(
      normalizedPoint(
        300,
        300,
        { left: 0, top: 0, width: 600, height: 600 },
        1080,
        1920,
      ),
    ).toEqual({ x: 0.5, y: 0.5, include: true });
    expect(
      normalizedPoint(
        0,
        300,
        { left: 0, top: 0, width: 600, height: 600 },
        1080,
        1920,
      ),
    ).toBeNull();
  });
  it("keeps adjacent frame timecodes distinct", () => {
    expect(timecode(1 / 24)).toBe("00:00:01");
    expect(timecode(1439 / 24)).toBe("00:59:23");
    expect(timecode(60)).toBe("01:00:00");
  });
});
