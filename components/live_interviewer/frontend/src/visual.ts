// Visual Engagement Coach — local, camera-only. Runs MediaPipe Face Landmarker
// entirely in the browser and feeds head-pose numbers to the pure
// VisualAccumulator. NO frames, screenshots, landmarks or biometric templates
// leave the browser or are stored — only the aggregated metrics are returned.
//
// Camera is opt-in and off by default (the caller only constructs this after the
// candidate accepts the disclaimer). Optional: the live interview runs without it.

import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { VisualAccumulator, VisualMetrics } from "./visualMetrics";

export class VisualCoach {
  private landmarker: FaceLandmarker | null = null;
  private video: HTMLVideoElement | null = null;
  private stream: MediaStream | null = null;
  private accumulator = new VisualAccumulator();
  private running = false;
  private startTime = 0;
  private raf = 0;

  async start(calibrationSeconds: number): Promise<void> {
    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
    );
    this.landmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath:
          "https://storage.googleapis.com/mediapipe-models/face_landmarker/" +
          "face_landmarker/float16/1/face_landmarker.task",
      },
      runningMode: "VIDEO",
      numFaces: 2, // detect >1 so multiple-faces lowers confidence
      outputFacialTransformationMatrixes: true,
    });

    this.stream = await navigator.mediaDevices.getUserMedia({ video: true });
    this.video = document.createElement("video");
    this.video.srcObject = this.stream;
    this.video.muted = true;
    await this.video.play();

    // Short calibration to learn this person/device's neutral orientation.
    const calib = await this.collect(calibrationSeconds);
    this.accumulator = new VisualAccumulator();
    this.accumulator.calibrate(calib);

    this.running = true;
    this.startTime = performance.now();
    this.loop();
  }

  private poseFromResult(result: any): { yaw: number; pitch: number } {
    // Derive yaw/pitch from the facial transformation matrix when available.
    const matrix = result.facialTransformationMatrixes?.[0]?.data;
    if (!matrix) return { yaw: 0, pitch: 0 };
    const yaw = Math.atan2(matrix[8], matrix[10]) * (180 / Math.PI);
    const pitch = Math.asin(-Math.max(-1, Math.min(1, matrix[9]))) * (180 / Math.PI);
    return { yaw, pitch };
  }

  private sampleOnce(now: number) {
    if (!this.landmarker || !this.video) return null;
    const result = this.landmarker.detectForVideo(this.video, now);
    const faceCount = result.faceLandmarks?.length ?? 0;
    if (faceCount === 0) {
      return { t: 0, facePresent: false, yaw: 0, pitch: 0, confidence: 0, faceCount };
    }
    const { yaw, pitch } = this.poseFromResult(result);
    // Presence + a coarse confidence proxy; no landmark data is retained.
    return { t: 0, facePresent: true, yaw, pitch, confidence: 0.9, faceCount };
  }

  private async collect(seconds: number) {
    const out: any[] = [];
    const end = performance.now() + seconds * 1000;
    while (performance.now() < end) {
      const s = this.sampleOnce(performance.now());
      if (s) out.push({ ...s, t: (performance.now() - end) / 1000 + seconds });
      await new Promise((r) => setTimeout(r, 100));
    }
    return out;
  }

  private loop = () => {
    if (!this.running) return;
    const s = this.sampleOnce(performance.now());
    if (s) {
      s.t = (performance.now() - this.startTime) / 1000;
      this.accumulator.add(s);
    }
    this.raf = window.setTimeout(this.loop, 100) as unknown as number;
  };

  // Aggregated coaching metrics only — safe to return to Python.
  finalize(): VisualMetrics {
    return this.accumulator.finalize();
  }

  stop(): void {
    this.running = false;
    if (this.raf) window.clearTimeout(this.raf);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.landmarker?.close();
    this.stream = null;
    this.video = null;
    this.landmarker = null;
  }
}
