import { describe, expect, it } from "vitest";

import { splitMarkers } from "./markers";

describe("splitMarkers", () => {
  it("interleaves text and markers", () => {
    expect(splitMarkers("Salary applies [1] and notice [12].")).toEqual([
      { kind: "text", value: "Salary applies " },
      { kind: "marker", n: 1 },
      { kind: "text", value: " and notice " },
      { kind: "marker", n: 12 },
      { kind: "text", value: "." },
    ]);
  });

  it("passes through plain text and ignores non-numeric brackets", () => {
    expect(splitMarkers("no markers [here]")).toEqual([{ kind: "text", value: "no markers [here]" }]);
  });
});
