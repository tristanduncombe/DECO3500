/* eslint-disable @typescript-eslint/no-explicit-any */
// app/utils/upload.ts
export type UploadResult = {
  ok: boolean;
  status: number;
  body: any;
};

export type UploadOptions = {
  url: string;
  action: "put" | "take";
  selfies: Blob[];
  foodPhoto?: Blob | null;
  token?: string | null;
  onProgress?: (percent: number) => void;
  fieldNames?: {
    selfies?: string;
    food?: string;
    action?: string;
  };
};

/**
 * Simple XMLHttpRequest-based uploader with progress callback.
 * Replace or extend this when your backend is ready.
 */
export default function uploadFridgeAction(opts: UploadOptions): Promise<UploadResult> {
  const {
    url,
    action,
    selfies,
    foodPhoto = null,
    token = null,
    onProgress = () => {},
    fieldNames = {},
  } = opts;

  const selfiesField = fieldNames.selfies ?? "selfies";
  const foodField = fieldNames.food ?? "food";
  const actionField = fieldNames.action ?? "action";

  return new Promise((resolve, reject) => {
    try {
      const fd = new FormData();
      fd.append(actionField, action);
      selfies.forEach((b, i) => fd.append(selfiesField, b, `selfie-${i + 1}.jpg`));
      if (foodPhoto) fd.append(foodField, foodPhoto, "food.jpg");

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);

      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (ev) => {
        if (!ev.lengthComputable) return;
        const percent = Math.round((ev.loaded / ev.total) * 100);
        try { onProgress(percent); } catch {}
      };

      xhr.onreadystatechange = () => {
        if (xhr.readyState !== XMLHttpRequest.DONE) return;
        const ct = xhr.getResponseHeader("content-type") || "";
        let body: any = null;
        try {
          if (ct.includes("application/json")) body = JSON.parse(xhr.responseText);
          else body = xhr.responseText;
        } catch {
          body = xhr.responseText;
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve({ ok: true, status: xhr.status, body });
        else resolve({ ok: false, status: xhr.status, body });
      };

      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.onabort = () => reject(new Error("Upload aborted"));

      xhr.send(fd);
    } catch (err) {
      reject(err);
    }
  });
}
