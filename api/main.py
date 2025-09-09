from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from sqlmodel import Field, SQLModel, Session, create_engine
from sqlalchemy.exc import OperationalError
import time
from fastapi.responses import FileResponse
import shutil
import os
from functools import lru_cache

app = FastAPI()

@lru_cache
def get_database_url() -> str:
    # Prefer env var (e.g., postgresql+psycopg://user:pass@host:port/db)
    return os.getenv("DATABASE_URL", "sqlite:///./inventory.db")

DATABASE_URL = get_database_url()
engine = None  # type: ignore

def init_engine_with_retry(max_attempts: int = 20, delay: float = 1.5):
    global engine
    attempt = 0
    while attempt < max_attempts:
        try:
            engine = create_engine(DATABASE_URL, echo=True)
            # test a connection
            with engine.connect() as conn:
                conn.execute("SELECT 1")  # simple validation
            return
        except OperationalError as e:
            attempt += 1
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to database after {max_attempts} attempts")

init_engine_with_retry()

IMAGES_DIR = "images"
os.makedirs(IMAGES_DIR, exist_ok=True)

class InventoryItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner: int
    item: str
    password_image: Optional[str] = None  # store filename
    display_image: Optional[str] = None   # store filename

SQLModel.metadata.create_all(engine)

# Health check
@app.get("/health")
def read_root():
    return {"status": "healthy"}

# POST: create an inventory item with images
@app.post("/inventory/items", response_model=InventoryItem)
def create_item(
    owner: int,
    item: str,
    password_image: UploadFile = File(...),
    display_image: UploadFile = File(...)
):
    password_path = os.path.join(IMAGES_DIR, password_image.filename)
    display_path = os.path.join(IMAGES_DIR, display_image.filename)

    # Save the image
    with open(password_path, "wb") as f:
        shutil.copyfileobj(password_image.file, f)
    with open(display_path, "wb") as f:
        shutil.copyfileobj(display_image.file, f)

    db_item = InventoryItem(
        owner=owner,
        item=item,
        password_image=password_image.filename,
        display_image=display_image.filename,
    )

    with Session(engine) as session:
        session.add(db_item)
        session.commit()
        session.refresh(db_item)
        return db_item

# GET: retrieve an inventory item
@app.get("/inventory/items/{item_id}", response_model=InventoryItem)
def get_item(item_id: int):
    with Session(engine) as session:
        item = session.get(InventoryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item

# GET: serve an image by filename
@app.get("/images/{filename}")
def get_image(filename: str):
    path = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)
