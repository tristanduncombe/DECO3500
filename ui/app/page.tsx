"use client";

import React, { useState } from "react";
import CameraCapture from "./components/CameraCapture";
import styles from "./page.module.css";

type Stage =
  | "idle"
  | "select"
  | "selfie"
  | "food"
  | "review"
  | "uploading"
  | "done";

type FoodItem = {
  id: string;
  label: string;
  thumbDataUrl: string;
};

const HARDCODED_FOOD: FoodItem[] = [
  {
    id: "apple-001",
    label: "Green Apple",
    thumbDataUrl:
      "data:image/svg+xml;utf8," +
      encodeURIComponent(
        `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='200'><rect width='100%' height='100%' fill='#f7fff7'/><circle cx='160' cy='100' r='46' fill='#60a561'/></svg>`
      ),
  },
  {
    id: "milk-001",
    label: "Milk Carton",
    thumbDataUrl:
      "data:image/svg+xml;utf8," +
      encodeURIComponent(
        `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='200'><rect width='100%' height='100%' fill='#fffdf7'/><rect x='120' y='35' width='80' height='110' rx='6' fill='#ffffff' stroke='#cbd5e1'/></svg>`
      ),
  },
  {
    id: "cheese-001",
    label: "Cheddar Slice",
    thumbDataUrl:
      "data:image/svg+xml;utf8," +
      encodeURIComponent(
        `<svg xmlns='http://www.w3.org/2000/svg' width='320' height='200'><rect width='100%' height='100%' fill='#fff8f0'/><rect x='50' y='50' width='220' height='100' rx='8' fill='#f6ad55' stroke='#e76f24'/></svg>`
      ),
  },
];

export default function Page() {
  const [mode, setMode] = useState<"put" | "take" | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [selfies, setSelfies] = useState<Blob[]>([]);
  const [foodPhoto, setFoodPhoto] = useState<Blob | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

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

  // Submit with selectedItemId included in FormData
  async function submit() {
    if (!mode) return;
    setStage("uploading");
    setMessage(null);

    const fd = new FormData();
    fd.append("action", mode);
    if (selectedItemId) fd.append("selectedItemId", selectedItemId);
    selfies.forEach((b, i) => fd.append("selfies", b, `selfie-${i + 1}.jpg`));
    if (foodPhoto) fd.append("food", foodPhoto, "food.jpg");

    try {
      // simplest approach: use uploadFridgeAction if you prefer,
      // here we do a direct XMLHttpRequest to ensure selectedItemId is sent
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "https://api.example.com/fridge/upload", true);
        xhr.upload.onprogress = (e) => {
          if (!e.lengthComputable) return;
          setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onreadystatechange = () => {
          if (xhr.readyState !== XMLHttpRequest.DONE) return;
          if (xhr.status >= 200 && xhr.status < 300) resolve();
          else reject(new Error(`Upload failed ${xhr.status}`));
        };
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(fd);
      });

      setMessage("Upload succeeded");
      setStage("done");
    } catch (err: unknown) {
      let msg = "Upload error";
      if (err instanceof Error) {
        msg = err.message;
      } else if (typeof err === "string") {
        msg = err;
      }
      setMessage(msg);
      setStage("review");
    }
  }

  return (
    <main className={styles.shell} role="main">
      <header className={styles.header}>
        <div className={styles.brand}>Smart Fridge</div>
        <div className={styles.modeHint}>{stage === "idle" ? "Tap to begin" : `Mode: ${mode?.toUpperCase()}`}</div>
      </header>

      <section className={styles.actions}>
        <button
          className={`${styles.bigBtn} ${styles.put}`}
          onClick={() => start("put")}
          disabled={stage !== "idle"}
          aria-label="Put item in fridge"
        >
          Put In
        </button>

        <button
          className={`${styles.bigBtn} ${styles.take}`}
          onClick={() => start("take")}
          disabled={stage !== "idle"}
          aria-label="Take item out of fridge"
        >
          Take Out
        </button>
      </section>

      {stage === "select" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Select Item to Remove</h2>
          <p className={styles.note}>Choose one of the known items below.</p>

          <div className={styles.selectionGrid}>
            {HARDCODED_FOOD.map((item) => {
              const selected = selectedItemId === item.id;
              return (
                <button
                  key={item.id}
                  className={`${styles.selectCard} ${selected ? styles.selected : ""}`}
                  onClick={() => setSelectedItemId(item.id)}
                  aria-pressed={selected}
                >
                  <img src={item.thumbDataUrl} alt={item.label} className={styles.selectThumb} />
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
              setStage("food");
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
                  <img key={i} src={URL.createObjectURL(b)} alt={`selfie ${i + 1}`} className={styles.previewThumb} />
                ))}
              </div>
            </div>

            <div className={styles.previewCard}>
              <div className={styles.previewTitle}>Food</div>
              <div className={styles.previewRow}>
                {foodPhoto ? (
                  <img src={URL.createObjectURL(foodPhoto)} alt="food" className={styles.foodLarge} />
                ) : (
                  <div className={styles.empty}>No food photo</div>
                )}

                {selectedItemId && (
                  <div className={styles.selectedInfo}>
                    <div className={styles.smallLabel}>Selected item</div>
                    <div className={styles.selectedWrap}>
                      <img
                        src={(HARDCODED_FOOD.find((f) => f.id === selectedItemId) as FoodItem).thumbDataUrl}
                        alt="selected"
                        className={styles.selectedThumb}
                      />
                      <div className={styles.selectedName}>
                        {(HARDCODED_FOOD.find((f) => f.id === selectedItemId) as FoodItem).label}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className={styles.footerRow}>
            <button className={styles.primary} onClick={submit}>
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
        <small>Pramith Made This Replace</small>
      </footer>
    </main>
  );
}
