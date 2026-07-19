// Split prose on [n] citation markers so text nodes can interleave chips.
// Pure and unit-tested; used by the DocumentPanel markdown renderer.

export type MarkerPart = { kind: "text"; value: string } | { kind: "marker"; n: number };

export function splitMarkers(text: string): MarkerPart[] {
  return text
    .split(/(\[\d+\])/)
    .filter(Boolean)
    .map((part) => {
      const m = /^\[(\d+)\]$/.exec(part);
      return m ? { kind: "marker" as const, n: Number(m[1]) } : { kind: "text" as const, value: part };
    });
}
