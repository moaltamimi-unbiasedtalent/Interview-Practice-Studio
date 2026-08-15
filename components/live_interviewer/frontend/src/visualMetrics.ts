// Pure, testable visual-engagement accumulator. Turns per-frame head/eye
// orientation samples (produced locally by MediaPipe Face Landmarker) into the
// small aggregated coaching metrics returned to Python. It holds NO frames and
// NO landmarks beyond the current head-pose numbers, and produces coaching
// metrics only — never an "attention score".

export interface FrameSample {
  t: number; // seconds since answer start
  facePresent: boolean;
  yaw: number; // degrees; + is turning right
  pitch: number; // degrees; + is looking down
  confidence: number; // 0..1 landmark confidence
  faceCount: number;
}

export interface VisualMetrics {
  face_present_percentage: number;
  screen_facing_percentage: number;
  longest_away_interval_seconds: number;
  number_of_extended_away_periods: number;
  excessive_head_turn_count: number;
  gaze_direction_proxy: string;
  landmark_confidence: number;
  multiple_faces: boolean;
}

const FACING_YAW_DEG = 15;
const FACING_PITCH_DEG = 15;
const HEAD_TURN_DEG = 25;
const EXTENDED_AWAY_SECONDS = 5;

export class VisualAccumulator {
  private baselineYaw = 0;
  private baselinePitch = 0;
  private samples: FrameSample[] = [];
  private multipleFaces = false;

  // Establish this person/device's neutral orientation — the exact camera
  // centre is not assumed to be reachable for every setup.
  calibrate(samples: FrameSample[]): void {
    const present = samples.filter((s) => s.facePresent);
    if (present.length === 0) return;
    this.baselineYaw = present.reduce((a, s) => a + s.yaw, 0) / present.length;
    this.baselinePitch = present.reduce((a, s) => a + s.pitch, 0) / present.length;
  }

  add(sample: FrameSample): void {
    if (sample.faceCount > 1) this.multipleFaces = true;
    this.samples.push(sample);
  }

  private facing(s: FrameSample): boolean {
    return (
      Math.abs(s.yaw - this.baselineYaw) <= FACING_YAW_DEG &&
      Math.abs(s.pitch - this.baselinePitch) <= FACING_PITCH_DEG
    );
  }

  finalize(): VisualMetrics {
    const n = this.samples.length;
    const empty: VisualMetrics = {
      face_present_percentage: 0,
      screen_facing_percentage: 0,
      longest_away_interval_seconds: 0,
      number_of_extended_away_periods: 0,
      excessive_head_turn_count: 0,
      gaze_direction_proxy: "unknown",
      landmark_confidence: 0,
      multiple_faces: this.multipleFaces,
    };
    if (n === 0) return empty;

    let totalTime = 0;
    let faceTime = 0;
    let facingTime = 0;
    let awayRun = 0;
    let longestAway = 0;
    let extended = 0;
    let turns = 0;
    let confSum = 0;
    let confCount = 0;
    let yawSum = 0;
    let pitchSum = 0;
    let prevYaw: number | null = null;

    for (let i = 0; i < n; i++) {
      const s = this.samples[i];
      const dt =
        i < n - 1
          ? Math.max(0, this.samples[i + 1].t - s.t)
          : i > 0
            ? Math.max(0, s.t - this.samples[i - 1].t)
            : 0;
      totalTime += dt;

      if (s.facePresent) {
        faceTime += dt;
        confSum += s.confidence;
        confCount += 1;
        yawSum += s.yaw - this.baselineYaw;
        pitchSum += s.pitch - this.baselinePitch;
        if (this.facing(s)) {
          facingTime += dt;
          if (awayRun >= EXTENDED_AWAY_SECONDS) extended += 1;
          awayRun = 0;
        } else {
          awayRun += dt;
          longestAway = Math.max(longestAway, awayRun);
        }
        if (prevYaw !== null && Math.abs(s.yaw - prevYaw) >= HEAD_TURN_DEG) turns += 1;
        prevYaw = s.yaw;
      } else {
        awayRun += dt;
        longestAway = Math.max(longestAway, awayRun);
      }
    }
    if (awayRun >= EXTENDED_AWAY_SECONDS) extended += 1;

    const facePct = totalTime > 0 ? (faceTime / totalTime) * 100 : 0;
    const facingPct = faceTime > 0 ? (facingTime / faceTime) * 100 : 0;
    const conf = confCount > 0 ? confSum / confCount : 0;
    const meanYaw = confCount > 0 ? yawSum / confCount : 0;
    const meanPitch = confCount > 0 ? pitchSum / confCount : 0;

    let gaze = "toward_screen";
    if (Math.abs(meanYaw) > FACING_YAW_DEG || Math.abs(meanPitch) > FACING_PITCH_DEG) {
      if (Math.abs(meanYaw) >= Math.abs(meanPitch)) gaze = meanYaw > 0 ? "right" : "left";
      else gaze = meanPitch > 0 ? "down" : "up";
    }

    return {
      face_present_percentage: round1(facePct),
      screen_facing_percentage: round1(facingPct),
      longest_away_interval_seconds: round1(longestAway),
      number_of_extended_away_periods: extended,
      excessive_head_turn_count: turns,
      gaze_direction_proxy: gaze,
      landmark_confidence: round2(conf),
      multiple_faces: this.multipleFaces,
    };
  }
}

function round1(v: number): number {
  return Math.round(v * 10) / 10;
}
function round2(v: number): number {
  return Math.round(v * 100) / 100;
}
