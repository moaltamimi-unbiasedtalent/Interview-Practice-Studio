import { describe, expect, it } from "vitest";
import { VisualAccumulator, FrameSample } from "../visualMetrics";

function sample(over: Partial<FrameSample> & { t: number }): FrameSample {
  return {
    facePresent: true,
    yaw: 0,
    pitch: 0,
    confidence: 0.9,
    faceCount: 1,
    ...over,
  };
}

describe("VisualAccumulator", () => {
  it("reports high screen-facing for a steady, forward answer", () => {
    const acc = new VisualAccumulator();
    for (let t = 0; t <= 20; t += 1) acc.add(sample({ t, yaw: 2, pitch: 1 }));
    const m = acc.finalize();
    expect(m.face_present_percentage).toBeGreaterThan(90);
    expect(m.screen_facing_percentage).toBeGreaterThan(90);
    expect(m.number_of_extended_away_periods).toBe(0);
    expect(m.gaze_direction_proxy).toBe("toward_screen");
    expect(m.multiple_faces).toBe(false);
  });

  it("detects an extended away period of more than 5 seconds", () => {
    const acc = new VisualAccumulator();
    // 0-3 s facing, 3-11 s turned far right (8 s away), 11-15 s facing again.
    for (let t = 0; t <= 3; t += 1) acc.add(sample({ t, yaw: 0 }));
    for (let t = 4; t <= 11; t += 1) acc.add(sample({ t, yaw: 40 }));
    for (let t = 12; t <= 15; t += 1) acc.add(sample({ t, yaw: 0 }));
    const m = acc.finalize();
    expect(m.number_of_extended_away_periods).toBe(1);
    expect(m.longest_away_interval_seconds).toBeGreaterThanOrEqual(5);
    expect(m.gaze_direction_proxy).toBe("right");
  });

  it("uses calibration to define neutral orientation", () => {
    const acc = new VisualAccumulator();
    // This person naturally sits with yaw ~20°; calibrate to that baseline.
    const calib = [0, 1, 2].map((t) => sample({ t, yaw: 20 }));
    acc.calibrate(calib);
    for (let t = 0; t <= 10; t += 1) acc.add(sample({ t, yaw: 21 }));
    const m = acc.finalize();
    // Relative to their baseline they are facing forward, not "away".
    expect(m.screen_facing_percentage).toBeGreaterThan(90);
  });

  it("flags multiple faces (low-confidence condition)", () => {
    const acc = new VisualAccumulator();
    acc.add(sample({ t: 0, faceCount: 2 }));
    acc.add(sample({ t: 1, faceCount: 2 }));
    expect(acc.finalize().multiple_faces).toBe(true);
  });

  it("returns empty metrics when there are no samples", () => {
    const m = new VisualAccumulator().finalize();
    expect(m.face_present_percentage).toBe(0);
    expect(m.landmark_confidence).toBe(0);
  });
});
