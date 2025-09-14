// app/fridge/page.tsx
'use client';

import { useRef, useState, useEffect } from 'react';

type Mode = 'select' | 'putIn' | 'takeOut';
type FridgeItem = { id: string; name: string; photoUrl: string };

export default function FridgePage() {
  const [mode, setMode] = useState<Mode>('select');
  const [items, setItems] = useState<FridgeItem[]>([]);
  const [itemName, setItemName] = useState('');
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [itemPhoto, setItemPhoto] = useState<string | null>(null);
  const [userPhoto, setUserPhoto] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  let stream: MediaStream;

  useEffect(() => {
    async function initCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch (e: any) {
        setError(`${e.name}: ${e.message}`);
      }
    }
    initCamera();
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, [mode]);

  const capture = (setter: (data: string) => void) => {
    if (!videoRef.current || !canvasRef.current) return;
    const v = videoRef.current;
    const c = canvasRef.current;
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    const ctx = c.getContext('2d');
    ctx?.drawImage(v, 0, 0);
    setter(c.toDataURL('image/png'));
  };

  const fetchItems = async () => {
    const res = await fetch('/api/fridge/items');
    setItems(await res.json());
  };

  const handlePutIn = async () => {
    if (!itemName || !itemPhoto || !userPhoto) return;
    await fetch('/api/fridge/addItem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: itemName, itemPhoto, userPhoto })
    });
    await fetchItems();
    reset();
  };

  const handleTakeOut = async () => {
    if (!selectedItemId || !userPhoto) return;
    await fetch('/api/fridge/removeItem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedItemId, userPhoto })
    });
    await fetchItems();
    reset();
  };

  const reset = () => {
    setMode('select');
    setItemName('');
    setSelectedItemId(null);
    setItemPhoto(null);
    setUserPhoto(null);
    setError(null);
  };

  useEffect(() => { if (mode === 'takeOut') fetchItems() }, [mode]);

  return (
    <main style={{ padding: '2rem', maxWidth: 500, margin: 'auto' }}>
      <h1>Smart Fridge</h1>

      {mode === 'select' && (
        <section>
          <button onClick={() => setMode('putIn')}>Put In Item</button>
          <button onClick={() => setMode('takeOut')}>Take Out Item</button>
        </section>
      )}

      {(mode === 'putIn' || mode === 'takeOut') && (
        <section style={{ marginTop: '1rem' }}>
          <button onClick={reset}>← Back</button>

          {mode === 'putIn' && (
            <>
              <input
                placeholder="Item name"
                value={itemName}
                onChange={(e) => setItemName(e.target.value)}
              />

              <div>
                <h2>Capture Item Photo</h2>
                <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%' }} />
                <button onClick={() => capture(setItemPhoto)}>Snap Item</button>
                {itemPhoto && <img src={itemPhoto} alt="item" style={{ maxWidth: '100%' }} />}
              </div>

              <div>
                <h2>Capture Your Photo</h2>
                <button onClick={() => capture(setUserPhoto)}>Snap Self</button>
                {userPhoto && <img src={userPhoto} alt="user" style={{ maxWidth: '100%' }} />}
              </div>

              <button onClick={handlePutIn} disabled={!itemName || !itemPhoto || !userPhoto}>
                Submit Put In
              </button>
            </>
          )}

          {mode === 'takeOut' && (
            <>
              <h2>Select Item to Take Out</h2>
              <ul>
                {items.map((it) => (
                  <li key={it.id}>
                    <label>
                      <input
                        type="radio"
                        name="fridgeItem"
                        value={it.id}
                        onChange={() => setSelectedItemId(it.id)}
                      />
                      {it.name}
                    </label>
                  </li>
                ))}
              </ul>

              <div>
                <h2>Capture Your Photo</h2>
                <button onClick={() => capture(setUserPhoto)}>Snap Self</button>
                {userPhoto && <img src={userPhoto} alt="user" style={{ maxWidth: '100%' }} />}
              </div>

              <button onClick={handleTakeOut} disabled={!selectedItemId || !userPhoto}>
                Submit Take Out
              </button>
            </>
          )}

          {error && <p style={{ color: 'red' }}>Error: {error}</p>}
        </section>
      )}

      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </main>
  );
}
