"use client";

import React, { useState } from "react";
import CameraCapture from "./components/CameraCapture";
import styles from "./page.module.css";
import { getAuthToken } from "./utils/useAuth"; // optional, may not exist

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

const MAX_FILES = 4;
const MAX_BYTES_PER_FILE = 10 * 1024 * 1024; // 10 MB, adjust as needed

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




  async function submit(): Promise<void> {
    if (!mode) return;
    setStage("uploading");
    setMessage(null);
    setProgress(0);

    try {
      // Normalize and client-side validation
      const normalizedSelfies: File[] = (selfies || [])
        .slice(0, MAX_FILES)
        .map((b, i) => (b instanceof File ? b : new File([b], `selfie-${i + 1}.jpg`, { type: b?.type || "image/jpeg" })));

      if (normalizedSelfies.length === 0) {
        throw new Error("No selfies to upload");
      }
      if (normalizedSelfies.length > MAX_FILES) {
        throw new Error(`Maximum ${MAX_FILES} selfies allowed`);
      }

      let normalizedFood: File | null = null;
      if (foodPhoto) {
        normalizedFood = foodPhoto instanceof File ? foodPhoto : new File([foodPhoto], "food.jpg", { type: (foodPhoto as any)?.type || "image/jpeg" });
      }

      for (const f of normalizedSelfies) {
        if (!f.type.startsWith("image/")) throw new Error(`${f.name} is not an image`);
        if (f.size > MAX_BYTES_PER_FILE) throw new Error(`${f.name} exceeds ${MAX_BYTES_PER_FILE} bytes`);
      }
      if (normalizedFood) {
        if (!normalizedFood.type.startsWith("image/")) throw new Error("Food photo is not an image");
        if (normalizedFood.size > MAX_BYTES_PER_FILE) throw new Error("Food photo is too large");
      }

      // Build FormData
      const fd = new FormData();
      fd.append("action", mode);
      if (selectedItemId) fd.append("selectedItemId", selectedItemId);
      normalizedSelfies.forEach((f) => fd.append("selfies", f, f.name));
      if (normalizedFood) fd.append("food", normalizedFood, normalizedFood.name);

      // Get auth token if available
      let token: string | null = null;
      if (typeof getAuthToken === "function") {
        try {
          token = await getAuthToken();
        } catch {
          token = null;
        }
      }

      // Send with XHR for upload progress
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "https://api.example.com/fridge/upload", true);

        if (token) {
          xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        }
        // If you rely on cookie auth and cross-origin, enable:
        // xhr.withCredentials = true;

        xhr.upload.onprogress = (e) => {
          if (!e.lengthComputable) return;
          setProgress(Math.round((e.loaded / e.total) * 100));
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) return resolve();
          try {
            const json = JSON.parse(xhr.responseText || "{}");
            return reject(new Error(json.detail || json.message || `Upload failed ${xhr.status}`));
          } catch {
            return reject(new Error(`Upload failed ${xhr.status}`));
          }
        };

        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.onabort = () => reject(new Error("Upload aborted"));

        // Do not set Content-Type; browser sets multipart boundary
        xhr.send(fd);
      });

      setProgress(100);
      setMessage("Upload succeeded");
      setStage("done");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === "string" ? err : "Upload error";
      setMessage(msg);
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
        <small>BLAH BLAH BLAH PRAMITH NEEDS TO ADD A FOOTER HERE OR SOMETHING</small>
      </footer>
    </main>
  );
}
