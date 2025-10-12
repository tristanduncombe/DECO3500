from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from src.password import build_fingerprint, compare_fingerprints, extract_body_and_hand_positions
from sqlmodel import Field, SQLModel, Session, create_engine
from sqlalchemy.exc import OperationalError
import time
from fastapi.encoders import jsonable_encoder
import shutil
import os
from functools import lru_cache
from sqlalchemy import text, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from uuid import uuid4
import requests

UNLOCK_THRESHOLD = 0.8

app = FastAPI()

@lru_cache
def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./inventory.db")
    # return "postgresql+psycopg://postgres:postgres@localhost:5432/deco"

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

IMAGES_DIR = "images"
os.makedirs(IMAGES_DIR, exist_ok=True)

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
    item: str,
    person_image: UploadFile = File(...),
    password_image: UploadFile = File(...)
):
    if person_image.filename is None or password_image.filename is None:
        raise HTTPException(status_code=400, detail="Image filename missing")

    person_path = os.path.join(IMAGES_DIR, person_image.filename)
    with open(person_path, "wb") as f:
        shutil.copyfileobj(person_image.file, f)

    pwd_path = os.path.join(IMAGES_DIR, password_image.filename)
    with open(pwd_path, "wb") as f:
        shutil.copyfileobj(password_image.file, f)

    db_item = InventoryItem(
        item=item,
        person_image=person_image.filename,
        password_image={"fingerprint": build_fingerprint(extract_body_and_hand_positions(pwd_path))},
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
        try:
            os.remove(pwd_path)
        except Exception:
            pass
        return jsonable_encoder(db_item)

@app.get("/inventory/items/{item_id}", response_model=InventoryItem)
def get_item(item_id: int):
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return jsonable_encoder(item)


@app.get("/inventory/items")
def list_items():
    with Session(engine) as session:
        try:
            res = session.exec(text("SELECT * FROM inventoryitem"))
            rows = res.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    out = []
    for r in rows:
        try:
            m = dict(r._mapping)
        except Exception:
            try:
                m = dict(r)
            except Exception:
                m = {str(i): v for i, v in enumerate(r)}
        out.append(m)

    return jsonable_encoder(out)


@app.post("/inventory/items/test", response_model=InventoryItem)
def create_test_item():
    """Create a test InventoryItem using a downloaded image for both person and password images."""
    url = "https://cdn.pixabay.com/photo/2019/03/12/20/39/girl-4051811_960_720.jpg"
    fname = "test_photo.jpg"
    path = os.path.join(IMAGES_DIR, fname)

    # download image
    resp = requests.get(url, stream=True, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to download test image")
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    # use same file for person and password photo in test
    person_filename = fname
    password_filename = f"test_password{os.path.splitext(fname)[1]}"
    password_path = os.path.join(IMAGES_DIR, password_filename)
    shutil.copyfile(path, password_path)

    db_item = InventoryItem(
        item="test",
        person_image=person_filename,
    # for test items compute and store fingerprint dict; remove raw file
    password_image={"fingerprint": build_fingerprint(extract_body_and_hand_positions(password_path))},
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
        try:
            os.remove(password_path)
        except Exception:
            pass
        return jsonable_encoder(db_item)


@app.post("/inventory/items/{item_id}/unlock")
def unlock_item(item_id: int, attempt_image: UploadFile = File(...)):
    """Upload a photo to attempt unlocking the item. Returns similarity score and success boolean."""
    # save attempt image to a temp path
    ext = os.path.splitext(attempt_image.filename or "")[1] or ".jpg"
    tmp_name = f"attempt_{uuid4().hex}{ext}"
    tmp_path = os.path.join(IMAGES_DIR, tmp_name)
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(attempt_image.file, f)

    try:
        attempt_positions = extract_body_and_hand_positions(tmp_path)
        attempt_fp = build_fingerprint(attempt_positions)

        with Session(engine) as session:
            item = session.get(InventoryItem, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            stored = item.password_image
            if not stored or not isinstance(stored, dict) or 'fingerprint' not in stored:
                raise HTTPException(status_code=400, detail="No stored fingerprint for this item")

            stored_fp = stored.get('fingerprint') or []
            score = compare_fingerprints(stored_fp, attempt_fp)
            success = score >= UNLOCK_THRESHOLD

            return jsonable_encoder({
                "item_id": item_id,
                "score": float(score),
                "success": bool(success),
            })
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


@app.get("/inventory/items/{item_id}/unlock/test")
def unlock_item_test(item_id: int):
    """Attempt unlock using the stored person/test image for this item."""
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    if not item.person_image:
        raise HTTPException(status_code=400, detail="No person image available for this item")

    person_path = os.path.join(IMAGES_DIR, item.person_image)
    if not os.path.exists(person_path):
        raise HTTPException(status_code=500, detail="Person image file missing on server")

    attempt_positions = extract_body_and_hand_positions(person_path)
    attempt_fp = build_fingerprint(attempt_positions)

    stored = item.password_image
    if not stored or not isinstance(stored, dict) or 'fingerprint' not in stored:
        raise HTTPException(status_code=400, detail="No stored fingerprint for this item")

    stored_fp = stored.get('fingerprint') or []
    score = compare_fingerprints(stored_fp, attempt_fp)
    success = score >= UNLOCK_THRESHOLD

    return jsonable_encoder({
        "item_id": item_id,
        "score": float(score),
        "success": bool(success),
    })
