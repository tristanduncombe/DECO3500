"use client";

/* eslint-disable @next/next/no-img-element */

import React, { useCallback, useEffect, useState } from "react";
import CameraCapture from "./components/CameraCapture";
import styles from "./page.module.css";
import { getAuthToken } from "./utils/useAuth";
import { Refrigerator, Sword } from "lucide-react";

type Stage = "idle" | "select" | "selfie" | "food" | "review" | "uploading" | "done";

type FoodItem = {
  id: string;
  label?: string | null;
  thumbDataUrl?: string | null;
  selfieDataUrl?: string | null;
};

const MAX_FILES = 4;
const MAX_SLOTS = 9;

export default function Page() {
  const [mode, setMode] = useState<"put" | "take" | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [selfies, setSelfies] = useState<Blob[]>([]);
  const [foodPhoto, setFoodPhoto] = useState<Blob | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string | null>(null);
  const [itemName, setItemName] = useState<string>("");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [foodItems, setFoodItems] = useState<FoodItem[]>([]);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [unlockExpiresAt, setUnlockExpiresAt] = useState<Date | null>(null);
  const [lockCountdown, setLockCountdown] = useState<number>(0);

  const fetchFoodItems = useCallback(async () => {
    setIsFetching(true);
    try {
      const res = await fetch(`/api/inventory/items`);
      if (!res.ok) {
        throw new Error(`Inventory request failed (${res.status})`);
      }
      const data = await res.json();
      const normalized: FoodItem[] = Array.isArray(data) ? data.slice(0, MAX_SLOTS) : [];
      setFoodItems(normalized);
      setInventoryError(null);
    } catch (err) {
      console.error("Failed to fetch food items", err);
      setFoodItems([]);
      setInventoryError("Unable to load fridge contents right now.");
    } finally {
      setIsFetching(false);
    }
  }, []);

  useEffect(() => {
    void fetchFoodItems();
  }, [fetchFoodItems]);

  useEffect(() => {
    let cancelled = false;
    const updateLockState = async () => {
      try {
        const res = await fetch(`/api/lock/state`, { cache: "no-store" });
        if (!res.ok) throw new Error(`Lock state request failed (${res.status})`);
        const data = await res.json();
        if (cancelled) return;
        if (!data.locked && data.unlock_expires_at) {
          const expiry = new Date(data.unlock_expires_at);
          if (!Number.isNaN(expiry.getTime())) {
            setUnlockExpiresAt(expiry);
            return;
          }
        }
        setUnlockExpiresAt(null);
      } catch (err) {
        if (!cancelled) console.error("Failed to fetch lock state", err);
      }
    };
    void updateLockState();
    const intervalId = window.setInterval(updateLockState, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (!unlockExpiresAt) {
      setLockCountdown(0);
      return;
    }
    const tick = () => {
      const diffMs = unlockExpiresAt.getTime() - Date.now();
      const diffSeconds = Math.ceil(diffMs / 1000);
      if (diffSeconds > 0) {
        setLockCountdown(diffSeconds);
      } else {
        setLockCountdown(0);
        setUnlockExpiresAt(null);
      }
    };
    tick();
    const timerId = window.setInterval(tick, 1000);
    return () => {
      window.clearInterval(timerId);
    };
  }, [unlockExpiresAt]);

  function start(action: "put" | "take") {
    setMode(action);
    setSelfies([]);
    setFoodPhoto(null);
    setProgress(0);
    setMessage(null);
    setItemName("");
    setSelectedItemId(null);
    setStage(action === "take" ? "select" : "selfie");
    void fetchFoodItems();
  }

  function reset() {
    setMode(null);
    setStage("idle");
    setSelfies([]);
    setFoodPhoto(null);
    setProgress(0);
    setMessage(null);
    setSelectedItemId(null);
    void fetchFoodItems();
  }

  async function submitPut(): Promise<void> {
    setStage("uploading");
    setMessage(null);
    setProgress(0);

    try {
      const trimmedItemName = itemName.trim();
      const normalizedSelfies: File[] = selfies.slice(0, MAX_FILES).map((b, i) =>
        b instanceof File ? b : new File([b], `selfie-${i + 1}.jpg`, { type: b?.type || "image/jpeg" })
      );

      if (normalizedSelfies.length !== 3) throw new Error("Exactly 3 selfies are required");
      if (!foodPhoto) throw new Error("Food photo is required");
      if (!trimmedItemName) throw new Error("Please enter a name for the item");

      const foodFile = new File([foodPhoto], "food.jpg", { type: foodPhoto.type || "image/jpeg" });

      const fd = new FormData();
      fd.append("item", trimmedItemName);
      fd.append("person_image", foodFile);
      normalizedSelfies.forEach((f, i) => fd.append(`password_image_${i + 1}`, f, f.name));

      const token = await getAuthToken?.();

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/inventory/items`, true);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        setProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          let result: { item?: string; unlock_expires_at?: string } | null = null;
          try {
            result = JSON.parse(xhr.responseText);
          } catch (parseErr) {
            console.warn("Unable to parse create item response", parseErr);
          }
          const label = typeof result?.item === "string" && result.item.trim() ? result.item.trim() : trimmedItemName;
          const expiresIso = typeof result?.unlock_expires_at === "string" ? result?.unlock_expires_at : null;
          if (expiresIso) {
            const expiry = new Date(expiresIso);
            if (!Number.isNaN(expiry.getTime())) {
              setUnlockExpiresAt(expiry);
            }
          }
          setMessage(`Fridge unlocked for 30 seconds. Place "${label}" inside now.`);
          setStage("done");
          setSelfies([]);
          setFoodPhoto(null);
          setItemName("");
          void fetchFoodItems();
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
    } catch (err) {
      const error = err as Error;
      setMessage(error.message || "Upload error");
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

      const url = `/api/inventory/items/${selectedItemId}/unlock`;

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
            const label: string = result.item || "Selected item";
            const expiresIso: string | null = result.unlock_expires_at || null;
            if (expiresIso) {
              const expiry = new Date(expiresIso);
              if (!Number.isNaN(expiry.getTime())) {
                setUnlockExpiresAt(expiry);
              }
            }
            setMessage(`Unlock successful! ${label} is unlocked.`);
            setStage("done");
            setSelectedItemId(null);
            if (typeof window !== "undefined") {
              setTimeout(() => {
                window.location.reload();
              }, 750);
            }
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
    } catch (err) {
      const error = err as Error;
      setMessage(error.message || "Upload error");
      setStage("review");
      setProgress(0);
    }
  }

  const isSelectionMode = stage === "select";
  const visibleItems = foodItems.slice(0, MAX_SLOTS);
  const emptySlots = Math.max(0, MAX_SLOTS - visibleItems.length);
  const shouldHideInventory = stage !== "idle" && stage !== "select";
  const countdownActive = lockCountdown > 0;
  const countdownLabel = countdownActive
    ? `${Math.floor(lockCountdown / 60)
        .toString()
        .padStart(2, "0")}:${(lockCountdown % 60).toString().padStart(2, "0")}`
    : "00:00";

  return (
    <main className={styles.shell} role="main">
      <header className={styles.header}>
        <div className={styles.brand + " flex items-center"}><Refrigerator />Fridge or Foe<Sword /></div>
        <div className={styles.modeHint}>
          {stage === "idle" ? "Choose an action to begin" : `Mode: ${mode?.toUpperCase() ?? "--"}`}
        </div>
      </header>

      {countdownActive && (
        <div className={`${styles.statusBanner} ${styles.statusUnlocked}`} role="status" aria-live="polite">
          <span>Fridge unlocked</span>
          <span className={styles.countdown}>{countdownLabel}</span>
        </div>
      )}

      <section className={styles.actions}>
        <button
          className={`${styles.bigBtn} ${styles.put}`}
          onClick={() => start("put")}
          disabled={stage !== "idle"}
          type="button"
        >
          Put In
        </button>
        <button
          className={`${styles.bigBtn} ${styles.take}`}
          onClick={() => start("take")}
          disabled={stage !== "idle"}
          type="button"
        >
          Take Out
        </button>
      </section>

      <section className={styles.inventoryPanel} aria-live="polite">
        <div className={styles.inventoryHeader}>
          <h2 className={styles.title}>Inside the fridge</h2>
          <span className={styles.slotCount}>
            {visibleItems.length}/{MAX_SLOTS}
          </span>
        </div>
        {inventoryError && <div className={styles.message}>{inventoryError}</div>}
        {shouldHideInventory ? (
          <div className={styles.inventoryOverlay}>
            {stage === "uploading"
              ? "Fridge view is hidden while uploads are processing…"
              : "Finish the current action to view inside the fridge again."}
          </div>
        ) : (
          <div className={styles.selectionGrid} aria-disabled={!isSelectionMode} data-stage={stage}>
            {visibleItems.map((item) => {
              const selected = selectedItemId === item.id;
              const label = item.label || "Unnamed item";
              const thumbSrc = item.thumbDataUrl || "/question-mark.png";
              const selfieSrc = item.selfieDataUrl || undefined;
              return (
                <button
                  type="button"
                  key={item.id}
                  className={`${styles.selectCard} ${selected ? styles.selected : ""}`}
                  onClick={() => {
                    if (!isSelectionMode) return;
                    setSelectedItemId(item.id);
                    setMessage(null);
                  }}
                  disabled={!isSelectionMode}
                  aria-pressed={isSelectionMode ? selected : undefined}
                >
                  <img
                    src={thumbSrc}
                    alt={label}
                    className={styles.selectThumb}
                    onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                  />
                  {selfieSrc && (
                    <img
                      src={selfieSrc}
                      alt="person"
                      className={styles.selfieThumb}
                      onError={(e) => (e.currentTarget.src = "/question-mark.png")}
                    />
                  )}
                  <div className={styles.selectLabel}>{label}</div>
                </button>
              );
            })}
            {Array.from({ length: emptySlots }).map((_, idx) => (
              <div key={`empty-${idx}`} className={`${styles.selectCard} ${styles.emptySlot}`}>
                <div className={styles.empty}>Empty slot</div>
              </div>
            ))}
          </div>
        )}
        {isFetching && <span className={styles.small}>Refreshing inventory…</span>}
      </section>

      {stage === "select" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Select Item to Remove</h2>
          <p className={styles.note}>Tap a slot above to highlight the item you want to unlock.</p>
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
              type="button"
            >
              Continue
            </button>
            <button className={styles.secondary} onClick={reset} type="button">
              Cancel
            </button>
          </div>
          {message && <div className={styles.message}>{message}</div>}
        </section>
      )}

      {stage === "selfie" && (
        <section className={styles.panel}>
          <h2 className={styles.title}>Selfies (3 shots)</h2>
          <p className={styles.note}>Tap Start, then pose. There’s a countdown before each shot.</p>
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
          {mode === "put" && (
            <div className={styles.inputGroup}>
              <label className={styles.inputLabel} htmlFor="item-name">Item name</label>
              <input
                id="item-name"
                type="text"
                value={itemName}
                onChange={(e) => setItemName(e.target.value)}
                className={styles.textInput}
                placeholder="e.g. Leftover curry"
                autoComplete="off"
              />
            </div>
          )}
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
            <button className={styles.primary} onClick={mode === "put" ? submitPut : submitTake} type="button">
              Submit
            </button>
            <button className={styles.secondary} onClick={reset} type="button">
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
            <button className={styles.secondary} onClick={reset} type="button">
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
            <button className={styles.primary} onClick={reset} type="button">
              Back
            </button>
          </div>
        </section>
      )}

      <footer className={styles.footer}>
        <small>© {new Date().getFullYear()} Fridge or Foe Team</small>
      </footer>
    </main>
  );
}
