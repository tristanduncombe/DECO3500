"use client";

import React, { useState, useEffect } from "react";
import CameraCapture from "./components/CameraCapture";
import styles from "./page.module.css";
import { getAuthToken } from "./utils/useAuth";

type Stage = "idle" | "select" | "selfie" | "food" | "review" | "uploading" | "done";

type FoodItem = {
  id: string;
  label: string;
  thumbDataUrl: string;
  selfieDataUrl?: string;
};

const MAX_FILES = 4;
const MAX_BYTES_PER_FILE = 10 * 1024 * 1024;

export default function Page() {
  const [mode, setMode] = useState<"put" | "take" | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [selfies, setSelfies] = useState<Blob[]>([]);
  const [foodPhoto, setFoodPhoto] = useState<Blob | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [foodItems, setFoodItems] = useState<FoodItem[]>([]);

  useEffect(() => {
    async function fetchFoodItems() {
      try {
        const res = await fetch("http://localhost:8000/inventory/items");
        const data = await res.json();
        setFoodItems(data || []);
      } catch (err) {
        console.error("Failed to fetch food items", err);
      }
    }

    fetchFoodItems();
  }, []);

  function start(action: "put" | "take") {
    setMode(action);
    setSelfies([]);
    setFoodPhoto(null);
    setProgress(0);
    setMessage(null);
    setSelectedItemId(null);
    setStage(action === "take" ? "select" : "selfie");
  }

  function reset() {
    setMode(null);
    setStage("idle");
    setSelfies([]);
    setFoodPhoto(null);
    setProgress(0);
    setMessage(null);
    setSelectedItemId(null);
  }

  async function submitPut(): Promise<void> {
    setStage("uploading");
    setMessage(null);
    setProgress(0);

    try {
      const normalizedSelfies: File[] = selfies.slice(0, MAX_FILES).map((b, i) =>
        b instanceof File ? b : new File([b], `selfie-${i + 1}.jpg`, { type: b?.type || "image/jpeg" })
      );

      if (normalizedSelfies.length !== 3) throw new Error("Exactly 3 selfies are required");
      if (!foodPhoto) throw new Error("Food photo is required");

      const foodFile = new File([foodPhoto], "food.jpg", { type: foodPhoto.type || "image/jpeg" });

      const fd = new FormData();
      fd.append("item", "New Item");
      fd.append("person_image", foodFile);
      normalizedSelfies.forEach((f, i) => fd.append(`password_image_${i + 1}`, f, f.name));

      const token = await getAuthToken?.();

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "http://localhost:8000/inventory/items", true);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        setProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          setMessage("Item successfully added to fridge");
          setStage("done");
        } else {
          setMessage(`Upload failed: ${xhr.status}`);
          setStage("review");
        }
      };
      xhr.onerror = () => {
        setMessage("Network error during upload");
        setStage("review");
      };
      xhr.send(fd);
    } catch (err: any) {
      setMessage(err.message || "Upload error");
      setStage("review");
      setProgress(0);
    }
  }

  async function submitTake(): Promise<void> {
    setStage("uploading");
    setMessage(null);
    setProgress(0);

    try {
      const normalizedSelfies: File[] = selfies.slice(0, MAX_FILES).map((b, i) =>
        b instanceof File ? b : new File([b], `selfie-${i + 1}.jpg`, { type: b?.type || "image/jpeg" })
      );

      if (normalizedSelfies.length !== 3) throw new Error("Exactly 3 selfies are required");
      if (!selectedItemId) throw new Error("No item selected");

      const fd = new FormData();
      normalizedSelfies.forEach((f, i) => fd.append(`attempt_image_${i + 1}`, f, f.name));

      const token = await getAuthToken?.();

      const url = `http://localhost:8000/inventory/items/${selectedItemId}/unlock`;

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        setProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const result = JSON.parse(xhr.responseText);
          if (result.success) {
            setMessage("Unlock successful! You may take the item.");
            setStage("done");
          } else {
            setMessage(`Unlock failed. Scores: ${result.scores.join(", ")}. Try again.`);
            setStage("review");
          }
        } else {
          setMessage(`Upload failed: ${xhr.status}`);
          setStage("review");
        }
      };
      xhr.onerror = () => {
        setMessage("Network error during upload");
        setStage("review");
      };
      xhr.send(fd);
    } catch (err: any) {
      setMessage(err.message || "Upload error");
      setStage("review");
      setProgress(0);
    }
  }

  return (
    <main className={styles.shell} role="main">
      <header className={styles.header}>
        <div className={styles.brand}>Smart Fridge</div>
        <div className={styles.modeHint}>{stage === "idle" ? "Tap to begin" : `Mode: ${mode?.toUpperCase()}`}</div>
      </header>

      <section className={styles.actions}>
        <button className={`${styles.bigBtn} ${styles.put}`} onClick={() => start("put")} disabled={stage !== "idle"}>
          Put In
        </button>
        <button className={`${styles.bigBtn} ${styles.take}`} onClick={() => start("take")} disabled={stage !== "idle"}>
          Take Out
        </button>
      </section>

      {stage === "select" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Select Item to Remove</h2>
          <p className={styles.note}>Choose one of the known items below.</p>
          <div className={styles.selectionGrid}>
            {foodItems.map((item) => {
              const selected = selectedItemId === item.id;
              return (
                <button
                  key={item.id}
                  className={`${styles.selectCard} ${selected ? styles.selected : ""}`}
                  onClick={() => setSelectedItemId(item.id)}
                  aria-pressed={selected}
                >
                  <img
                    src={item.thumbDataUrl}
                    alt={item.label}
                    className={styles.selectThumb}
                    onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                  />
                  {item.selfieDataUrl && (
                    <img
                      src={item.selfieDataUrl}
                      alt="person"
                      className={styles.selfieThumb}
                      onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                    />
                  )}
                  <div className={styles.selectLabel}>{item.label}</div>
                </button>
              );
            })}
          </div>
          <div className={styles.footerRow}>
            <button
              className={styles.primary}
              onClick={() => {
                if (!selectedItemId) {
                  setMessage("Please select an item first");
                  return;
                }
                setMessage(null);
                setStage("selfie");
              }}
            >
              Continue
            </button>
            <button className={styles.secondary} onClick={reset}>
              Cancel
            </button>
          </div>
          {message && <div className={styles.message}>{message}</div>}
        </section>
      )}

      {stage === "selfie" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Selfies (up to 3)</h2>
          <p className={styles.note}>Tap Start, then pose. Countdown before each shot.</p>
          <CameraCapture
            shots={3}
            label="Selfie"
            onComplete={(imgs) => {
              setSelfies(imgs);
              setStage(mode === "put" ? "food" : "review");
            }}
            onCancel={reset}
          />
        </section>
      )}

      {stage === "food" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Food Photo</h2>
          <p className={styles.note}>Capture the item clearly.</p>
          <CameraCapture
            shots={1}
            label="Food"
            onComplete={(imgs) => {
              setFoodPhoto(imgs[0]);
              setStage("review");
            }}
            onCancel={reset}
          />
        </section>
      )}

      {stage === "review" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Review</h2>
          <div className={styles.previewGrid}>
            <div className={styles.previewCard}>
              <div className={styles.previewTitle}>Selfies</div>
              <div className={styles.previewRow}>
                {selfies.length === 0 && <div className={styles.empty}>No selfies</div>}
                {selfies.map((b, i) => (
                  <img
                    key={i}
                    src={URL.createObjectURL(b)}
                    alt={`selfie ${i + 1}`}
                    className={styles.selfieThumb}
                    onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                  />
                ))}
              </div>
            </div>

            {mode === "put" && (
              <div className={styles.previewCard}>
                <div className={styles.previewTitle}>Food</div>
                <div className={styles.previewRow}>
                  {foodPhoto ? (
                    <img
                      src={URL.createObjectURL(foodPhoto)}
                      alt="food"
                      className={styles.foodLarge}
                      onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                    />
                  ) : (
                    <div className={styles.empty}>No food photo</div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className={styles.footerRow}>
            <button
              className={styles.primary}
              onClick={mode === "put" ? submitPut : submitTake}
            >
              Submit
            </button>
            <button className={styles.secondary} onClick={reset}>
              Cancel
            </button>
          </div>

          {message && <div className={styles.message}>{message}</div>}
        </section>
      )}

      {stage === "uploading" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Uploading</h2>
          <div className={styles.progressWrap}>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${progress}%` }} />
            </div>
            <div className={styles.progressText}>{progress}%</div>
          </div>
          <div className={styles.footerRow}>
            <button className={styles.secondary} onClick={reset}>
              Abort
            </button>
          </div>
        </section>
      )}

      {stage === "done" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Done</h2>
          <div className={styles.message}>{message}</div>
          <div className={styles.footerRow}>
            <button className={styles.primary} onClick={reset}>
              Back
            </button>
          </div>
        </section>
      )}

      <footer className={styles.footer}>
        <small>BLAH BLAH BLAH PRAMITH NEEDS TO ADD A FOOTER HERE OR SOMETHING</small>
      </footer>
    </main>
  );
}
