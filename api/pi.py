from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from src.password import build_fingerprint, compare_fingerprints, extract_body_and_hand_positions
from sqlmodel import Field, SQLModel, Session, create_engine
from sqlalchemy.exc import OperationalError
import time
from fastapi.encoders import jsonable_encoder
import shutil
import os
import base64
from functools import lru_cache
from sqlalchemy import text, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from uuid import uuid4
import logging
import tempfile

UNLOCK_THRESHOLD = 0.8

app = FastAPI()

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

# CORS setup: restrict to specific origins by default; override via CORS_ORIGINS env (comma separated)
DEFAULT_CORS_ORIGINS = [
    "http://103.249.239.235",
    "https://103.249.239.235",
]

_cors_origins = os.getenv("CORS_ORIGINS")
if _cors_origins and _cors_origins.strip():
    if _cors_origins.strip() == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    origins = DEFAULT_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache
def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5431/deco")

DATABASE_URL = get_database_url()
engine = None

def init_engine_with_retry(max_attempts: int = 20, delay: float = 1.5):
    global engine
    attempt = 0
    while attempt < max_attempts:
        try:
            engine = create_engine(DATABASE_URL, echo=True)
            # test a connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            attempt += 1
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to database after {max_attempts} attempts")

init_engine_with_retry()

BASE_DIR = os.path.dirname(__file__)
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def _remove_file_if_exists(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.warning("Failed to remove file %s", path, exc_info=True)

class InventoryItem(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    item: str
    person_image: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    password_image: Optional[dict] = Field(default=None, sa_column=Column(JSONB, nullable=True))

    class Config:
        table = True

SQLModel.metadata.create_all(engine)

@app.post("/inventory/items", response_model=InventoryItem)
def create_item(
    item: str = Form(...),
    person_image: UploadFile = File(...),
    password_image_1: UploadFile = File(...),
    password_image_2: UploadFile = File(...),
    password_image_3: UploadFile = File(...),
):
    # validate inputs
    if (
        person_image.filename is None
        or password_image_1.filename is None
        or password_image_2.filename is None
        or password_image_3.filename is None
    ):
        raise HTTPException(status_code=400, detail="Image filename missing")

    # save files using UUID filenames (preserve extension)
    def _save_upload(upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or '')[1] or '.jpg'
        fname = f"{uuid4().hex}{ext}"
        path = os.path.join(IMAGES_DIR, fname)
        with open(path, 'wb') as f:
            shutil.copyfileobj(upload.file, f)
        return fname

    person_fname = _save_upload(person_image)

    # For password images, use temporary files (do not persist filenames)
    def _save_temp_upload(upload: UploadFile) -> str:
        ext = os.path.splitext(upload.filename or '')[1] or '.jpg'
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=IMAGES_DIR)
        with tmp as f:
            shutil.copyfileobj(upload.file, f)
        return tmp.name

    pwd1 = _save_temp_upload(password_image_1)
    pwd2 = _save_temp_upload(password_image_2)
    pwd3 = _save_temp_upload(password_image_3)

    # extract positions and fingerprints for each password image
    pos1 = extract_body_and_hand_positions(pwd1)
    pos2 = extract_body_and_hand_positions(pwd2)
    pos3 = extract_body_and_hand_positions(pwd3)

    fp1 = build_fingerprint(pos1)
    fp2 = build_fingerprint(pos2)
    fp3 = build_fingerprint(pos3)

    # validate fingerprints: if extraction failed (empty fingerprint), reject the upload
    if not fp1 or not fp2 or not fp3:
        # log details for debugging
        logger.warning("Fingerprint extraction failed for one or more password images: sizes=%s,%s,%s", len(fp1), len(fp2), len(fp3))
        logger.debug("pos1=%s", pos1)
        logger.debug("pos2=%s", pos2)
        logger.debug("pos3=%s", pos3)
        raise HTTPException(status_code=400, detail="Could not detect pose/hand landmarks in one or more password images")

    db_item = InventoryItem(
        item=item,
        person_image=person_fname,
        password_image={
            "fingerprints": [fp1, fp2, fp3],
        },
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
    # cleanup temporary password images immediately (never persist)
    try:
        os.remove(pwd1)
    except Exception:
        pass
    try:
        os.remove(pwd2)
    except Exception:
        pass
    try:
        os.remove(pwd3)
    except Exception:
        pass

    # embed person image bytes and password images as data URLs in the returned payload
    out = jsonable_encoder(db_item)
    try:
        imgpath = os.path.join(IMAGES_DIR, db_item.person_image) if db_item.person_image else None
        if imgpath and os.path.exists(imgpath):
            ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
            with open(imgpath, 'rb') as f:
                b = f.read()
            out['person_image'] = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
    except Exception:
        out['person_image'] = db_item.person_image

    # Do not include or persist any password image data in the response

    return out

@app.get("/inventory/items/{item_id}", response_model=InventoryItem)
def get_item(item_id: int):
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        out = jsonable_encoder(item)
        try:
            imgpath = os.path.join(IMAGES_DIR, item.person_image) if item.person_image else None
            if imgpath and os.path.exists(imgpath):
                ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
                with open(imgpath, 'rb') as f:
                    b = f.read()
                out['person_image'] = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
        except Exception:
            out['person_image'] = item.person_image

        return out


@app.get("/inventory/items")
def list_items():
    with Session(engine) as session:
        try:
            res = session.exec(text("SELECT * FROM inventoryitem"))
            rows = res.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    items = []
    for r in rows:
        try:
            m = dict(r._mapping)
        except Exception:
            try:
                m = dict(r)
            except Exception:
                m = {str(i): v for i, v in enumerate(r)}

        person_value = m.get('person_image')
        person_data_url = None
        try:
            if isinstance(person_value, str) and person_value:
                if person_value.startswith('data:'):
                    person_data_url = person_value
                else:
                    imgpath = os.path.join(IMAGES_DIR, person_value)
                    if os.path.exists(imgpath):
                        ext = os.path.splitext(imgpath)[1].lstrip('.') or 'jpeg'
                        with open(imgpath, 'rb') as f:
                            b = f.read()
                        person_data_url = f"data:image/{ext};base64,{base64.b64encode(b).decode('ascii') }"
        except Exception:
            person_data_url = person_value if isinstance(person_value, str) else None

        # We no longer store password image files; omit them from listing
        password_urls = []

        selfie_data_url = next((url for url in password_urls if url), None)
        item_id = m.get('id')

        items.append({
            "id": str(item_id) if item_id is not None else None,
            "label": m.get('item'),
            "thumbDataUrl": person_data_url or "",
            "selfieDataUrl": selfie_data_url,
            "passwordImageUrls": password_urls or None,
        })

    return jsonable_encoder(items)


# Solenoid controller bootstrap (Raspberry Pi)
try:
    solenoid  # type: ignore[name-defined]
    GPIO_UNLOCK_SECONDS  # type: ignore[name-defined]
except NameError:
    # Prefer RPi.GPIO; fallback to libgpiod for Pi 5/new kernels
    try:
        import RPi.GPIO as GPIO  # type: ignore
        HAS_GPIO = True
    except Exception:
        HAS_GPIO = False
        # Minimal stub to satisfy linters/type-checkers when GPIO is unavailable
        class _GPIOStub:
            BCM = 11
            BOARD = 10
            HIGH = 1
            LOW = 0
            OUT = 0
            def setwarnings(self, *a, **k): pass
            def setmode(self, *a, **k): pass
            def setup(self, *a, **k): pass
            def output(self, *a, **k): pass
        GPIO = _GPIOStub()  # type: ignore
    try:
        import gpiod  # type: ignore
        HAS_GPIOD = True
    except Exception:
        HAS_GPIOD = False
        # Minimal stub for libgpiod symbols to avoid lint errors
        class _GpiodStub:
            class LineDirection:
                OUTPUT = 1
            class LineSettings:
                def __init__(self, *a, **k): pass
            LINE_REQ_DIR_OUT = 1
            class Chip:
                def __init__(self, *a, **k): pass
                def request_lines(self, *a, **k):
                    class _Req:
                        def set_values(self, *a, **k): pass
                    return _Req()
                def get_line(self, *a, **k):
                    class _Line:
                        def request(self, *a, **k): pass
                        def set_value(self, *a, **k): pass
                    return _Line()
        gpiod = _GpiodStub()  # type: ignore

    class SolenoidController:
        def __init__(self, pin: int, active_low: bool = True):
            self.pin = pin
            self.active_low = active_low
            self.initialized = False
            self._backend = None  # 'RPi' or 'gpiod'
            # Backend 1: RPi.GPIO
            if HAS_GPIO:
                try:
                    GPIO.setwarnings(False)
                    GPIO.setmode(GPIO.BCM)
                    initial_level = GPIO.HIGH if self.active_low else GPIO.LOW
                    GPIO.setup(self.pin, GPIO.OUT, initial=initial_level)
                    self._backend = 'RPi'
                    self.initialized = True
                    return
                except Exception:
                    logger.exception("Failed to initialize RPi.GPIO; trying gpiod")
            # Backend 2: libgpiod
            if HAS_GPIOD:
                try:
                    # Chip selection: default gpiochip0
                    try:
                        chip = gpiod.Chip('gpiochip0')  # libgpiod v2 preferred
                    except Exception:
                        chip = gpiod.Chip(0)  # fallback
                    self._chip = chip
                    # Configure line as output with initial OFF level
                    off_val = 1 if self.active_low else 0
                    try:
                        # libgpiod v2 API
                        cfg = {self.pin: gpiod.LineSettings(direction=gpiod.LineDirection.OUTPUT,
                                                             output_value=off_val)}
                        self._req = chip.request_lines(consumer='deco-solenoid', config=cfg)
                    except Exception:
                        # libgpiod v1 API
                        line = chip.get_line(self.pin)
                        line.request(consumer='deco-solenoid', type=gpiod.LINE_REQ_DIR_OUT, default_vals=[off_val])
                        self._line = line
                    self._backend = 'gpiod'
                    self.initialized = True
                except Exception:
                    logger.exception("Failed to initialize libgpiod; solenoid control disabled")

        def _on_level(self):
            # Energize solenoid
            if self._backend == 'RPi':
                return GPIO.LOW if self.active_low else GPIO.HIGH
            # gpiod uses 0/1
            return 0 if self.active_low else 1

        def _off_level(self):
            # De-energize solenoid
            if self._backend == 'RPi':
                return GPIO.HIGH if self.active_low else GPIO.LOW
            return 1 if self.active_low else 0

        def set_locked(self, locked: bool = True):
            if not self.initialized:
                return
            try:
                if self._backend == 'RPi':
                    GPIO.output(self.pin, self._off_level() if locked else self._on_level())
                elif self._backend == 'gpiod':
                    val = self._off_level() if locked else self._on_level()
                    if hasattr(self, '_req'):
                        self._req.set_values({self.pin: val})
                    else:
                        self._line.set_value(val)
            except Exception:
                logger.exception("GPIO output failed")

        def unlock_for(self, seconds: float = 30.0):
            if not self.initialized:
                logger.warning("GPIO not available; simulated unlock for %ss", seconds)
                time.sleep(seconds)
                return
            try:
                # Unlock (energize)
                if self._backend == 'RPi':
                    GPIO.output(self.pin, self._on_level())
                else:
                    val = self._on_level()
                    if hasattr(self, '_req'):
                        self._req.set_values({self.pin: val})
                    else:
                        self._line.set_value(val)
                time.sleep(seconds)
            finally:
                # Relock (de-energize)
                try:
                    if self._backend == 'RPi':
                        GPIO.output(self.pin, self._off_level())
                    else:
                        val = self._off_level()
                        if hasattr(self, '_req'):
                            self._req.set_values({self.pin: val})
                        else:
                            self._line.set_value(val)
                except Exception:
                    logger.exception("Failed to relock solenoid after unlock window")

    GPIO_PIN = int(os.getenv("GPIO_PIN", "18"))
    GPIO_ACTIVE_LOW = os.getenv("GPIO_ACTIVE_LOW", "1").lower() in ("1", "true", "yes", "on")
    GPIO_UNLOCK_SECONDS = float(os.getenv("GPIO_UNLOCK_SECONDS", "30"))

    solenoid = SolenoidController(pin=GPIO_PIN, active_low=GPIO_ACTIVE_LOW)
    # Ensure locked on startup
    solenoid.set_locked(True)

@app.post("/inventory/items/{item_id}/unlock")
def unlock_item(
    item_id: int,
    attempt_image_1: UploadFile = File(...),
    attempt_image_2: UploadFile = File(...),
    attempt_image_3: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    """Upload three photos to attempt unlocking the item. Returns per-image similarity scores and overall success."""
    # save attempts to temp files
    tmp1 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_1.filename or '1'}")
    tmp2 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_2.filename or '2'}")
    tmp3 = os.path.join(IMAGES_DIR, f"attempt_{uuid4().hex}_{attempt_image_3.filename or '3'}")
    with open(tmp1, "wb") as f:
        shutil.copyfileobj(attempt_image_1.file, f)
    with open(tmp2, "wb") as f:
        shutil.copyfileobj(attempt_image_2.file, f)
    with open(tmp3, "wb") as f:
        shutil.copyfileobj(attempt_image_3.file, f)

    try:
        afp1 = build_fingerprint(extract_body_and_hand_positions(tmp1))
        afp2 = build_fingerprint(extract_body_and_hand_positions(tmp2))
        afp3 = build_fingerprint(extract_body_and_hand_positions(tmp3))

        with Session(engine) as session:
            item = session.get(InventoryItem, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            stored = item.password_image or {}

            if 'fingerprints' in stored and isinstance(stored['fingerprints'], list) and len(stored['fingerprints']) >= 3:
                sp1, sp2, sp3 = stored['fingerprints'][:3]
            elif 'fingerprint' in stored:
                # legacy single fingerprint -> compare same fingerprint to all attempts
                sp = stored.get('fingerprint') or []
                sp1 = sp2 = sp3 = sp
            else:
                raise HTTPException(status_code=400, detail="Stored fingerprint format unsupported")

            s1 = compare_fingerprints(sp1, afp1)
            s2 = compare_fingerprints(sp2, afp2)
            s3 = compare_fingerprints(sp3, afp3)

            avg = float((s1 + s2 + s3) / 3.0)
            success = avg >= UNLOCK_THRESHOLD

            response_payload = {
                "item_id": item_id,
                "scores": [float(s1), float(s2), float(s3)],
                "average": avg,
                "success": bool(success),
            }

            if success:
                # Trigger solenoid unlock in the background (non-blocking)
                if background_tasks is not None:
                    background_tasks.add_task(solenoid.unlock_for, GPIO_UNLOCK_SECONDS)
                else:
                    import threading
                    threading.Thread(target=solenoid.unlock_for, args=(GPIO_UNLOCK_SECONDS,), daemon=True).start()

                # Remove the item after successful unlock (cleanup)
                session.delete(item)
                session.commit()

            return response_payload
    except Exception as e:
        logger.exception("Unlock failed")
        raise HTTPException(status_code=500, detail=f"Unlock failed: {e}")
    finally:
        _remove_file_if_exists(tmp1)
        _remove_file_if_exists(tmp2)
        _remove_file_if_exists(tmp3)


