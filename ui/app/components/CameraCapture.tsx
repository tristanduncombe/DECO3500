// app/components/CameraCapture.tsx
"use client";

import React, { useEffect, useRef, useState } from "react";
import styles from "../page.module.css";

type Props = {
  shots?: number; // default 1
  label?: string;
  countdownStart?: number; // default 3
  onComplete: (images: Blob[]) => void;
  onCancel?: () => void;
};

export default function CameraCapture({
  shots = 1,
  label = "Photo",
  countdownStart = 3,
  onComplete,
  onCancel,
}: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [captured, setCaptured] = useState<Blob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function start() {
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
        if (!mounted) {
          s.getTracks().forEach(t => t.stop());
          return;
        }
        streamRef.current = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          await videoRef.current.play();
        }
      } catch (e) {
        setError("Camera access denied or unavailable");
      }
    }
    start();
    return () => {
      mounted = false;
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  useEffect(() => {
    if (countdown === null) return;
    if (countdown <= 0) {
      capture();
      return;
    }
    const id = window.setTimeout(() => setCountdown(c => (c === null ? null : c - 1)), 1000);
    return () => clearTimeout(id);
  }, [countdown]);

  function startCountdown() {
    setCountdown(countdownStart);
  }

  async function capture() {
    const video = videoRef.current;
    if (!video) return;
    if (!canvasRef.current) canvasRef.current = document.createElement("canvas");
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setError("Cannot capture image");
      return;
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob: Blob | null = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) {
      setError("Capture failed");
      return;
    }
    const next = [...captured, blob];
    setCaptured(next);
    setCountdown(null);

    if (next.length >= shots) {
      streamRef.current?.getTracks().forEach(t => t.stop());
      onComplete(next);
    } else {
      // tiny delay before next countdown so UI updates
      setTimeout(() => setCountdown(countdownStart), 600);
    }
  }

  function handleCancel() {
    streamRef.current?.getTracks().forEach(t => t.stop());
    onCancel?.();
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ fontWeight: 700 }}>{label}</div>
      {error && <div style={{ color: "crimson" }}>{error}</div>}
      <div style={{ position: "relative", width: "100%", height: "100%", background: "#000" }}>
        <video
          ref={videoRef}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: "scaleX(-1)" // mirror the camera preview
          }}
        />
        {countdown !== null && (
          <div style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 64,
            color: "white",
            background: "rgba(0,0,0,0.35)"
          }}>
            {countdown}
          </div>
        )}
      </div>
      <div className={styles.btnInlineGroup}>
        <button
          type="button"
          className={`${styles.primary} ${styles.inlineBtn}`}
          onClick={startCountdown}
          aria-label="Start countdown"
        >
          Start
        </button>

        <button
          type="button"
          className={`${styles.secondary} ${styles.inlineBtn}`}
          onClick={handleCancel}
          aria-label="Cancel capture"
        >
          Cancel
        </button>
      </div>

      <div>
        <small className={styles.small}>Captured {captured.length} of {shots}</small>
      </div>
    </div>
  );
}
