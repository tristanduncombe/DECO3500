# FridgeOrFoe

_Shared fridges often suffer petty food theft and low social interaction; this project deters casual theft while encouraging playful, meaningful interactions around food._

![Fridge or Foe UI](images/readme-ui.png)

FridgeOrFoe is a small prototype demonstrating a server-backed smart lock for a shared fridge. It includes:
- A FastAPI backend that stores inventory items and manages a short unlock window.
- A browser UI (Next.js) for adding/removing items and capturing/uploading photos.
- A Raspberry Pi client that polls lock state and drives a solenoid via libgpiod.

Contents
- API service: [api/main.py](api/main.py)
- API helpers: [api/src/password.py](api/src/password.py) (key functions: [`src.password.extract_body_and_hand_positions`](api/src/password.py), [`src.password.build_fingerprint`](api/src/password.py), [`src.password.compare_fingerprints`](api/src/password.py))
- UI: [ui/app/page.tsx](ui/app/page.tsx) and components such as [`CameraCapture`](ui/app/components/CameraCapture.tsx)
- UI utils: [`getApiBase`](ui/app/utils/api.ts), [`getAuthToken`](ui/app/utils/useAuth.ts), and the uploader [`uploadFridgeAction`](ui/app/utils/upload.ts)
- Pi client: [client/main.py](client/main.py)
- Docker orchestration: [docker-compose.yml](docker-compose.yml)
- Dockerfiles: [api/Dockerfile](api/Dockerfile), [ui/Dockerfile](ui/Dockerfile)
- UI README: [ui/README.md](ui/README.md)

Quick start (Docker, recommended)
1. From project root:
   npm: docker compose up --build
2. Services:
   - API: http://localhost:8000 — docs: http://localhost:8000/docs
   - UI:  http://localhost:3000

Example API endpoints
- Get lock state
  curl -s http://localhost:8000/lock/state | jq
- Set lock (lock)
  curl -X POST -H "Content-Type: application/json" -d '{"locked": true}' http://localhost:8000/lock/state
- Unlock for N seconds
  curl -X POST -H "Content-Type: application/json" -d '{"locked": false, "unlock_duration": 20}' http://localhost:8000/lock/state

How it works (high level)
- Adding an item (UI POST to `/inventory/items`) uploads a person image and three "password" images. The backend:
  - Saves the person image (persisted under `api/images`) and temporarily processes the three password photos.
  - Extracts pose/hand landmarks via [`src.password.extract_body_and_hand_positions`](api/src/password.py) and converts those to a compact fingerprint via [`src.password.build_fingerprint`](api/src/password.py).
  - Stores the item record (with fingerprints) and opens the lock for a short window (configurable in [api/main.py](api/main.py) via `UNLOCK_WINDOW_SECONDS` and `UNLOCK_THRESHOLD`).
- Unlocking an item uploads three attempt images to `/inventory/items/{id}/unlock`. The backend computes fingerprints and compares with stored fingerprints using [`src.password.compare_fingerprints`](api/src/password.py). On success the item is removed and the lock opens briefly.

Development notes
- The UI proxies API requests using server route handlers in [ui/app/api/_backend.ts](ui/app/api/_backend.ts) and the client page uses [`getApiBase`](ui/app/utils/api.ts) to determine base URL.
- The UI uses client-side captures with [ui/app/components/CameraCapture.tsx](ui/app/components/CameraCapture.tsx) and uploads via [`uploadFridgeAction`](ui/app/utils/upload.ts).
- The Pi client in [client/main.py](client/main.py) polls `/lock/state` and toggles a GPIO line using libgpiod. Adjust `BACKEND_BASE_URL` if your API is not at the default address.

Testing & troubleshooting
- If the API fails to connect to the DB, check container logs and ensure the DB service is healthy (see [docker-compose.yml](docker-compose.yml)).
- Uploaded images are persisted to the `api_images` Docker volume (mounted to `api/images`) — this is configured in [docker-compose.yml](docker-compose.yml).
- If camera access fails in the browser, confirm permissions and that the device has a camera. The capture component mirrors the preview for selfies.

Security & privacy
- Password photos are processed and not persisted; only fingerprint vectors are stored (see [api/src/password.py](api/src/password.py) for sanitization logic).
- The backend exposes CORS origins controlled by the `CORS_ORIGINS` environment variable (configured in [docker-compose.yml](docker-compose.yml)); adjust for your deployment.

Useful files to inspect
- Backend API and routes: [api/main.py](api/main.py)
- Fingerprint/vision utilities: [api/src/password.py](api/src/password.py)
- UI entry: [ui/app/page.tsx](ui/app/page.tsx)
- UI server-side proxy helpers: [ui/app/api/_backend.ts](ui/app/api/_backend.ts)
- Pi client: [client/main.py](client/main.py)
- Compose orchestration: [docker-compose.yml](docker-compose.yml)
- UI Dockerfile: [ui/Dockerfile](ui/Dockerfile)
- API Dockerfile: [api/Dockerfile](api/Dockerfile)