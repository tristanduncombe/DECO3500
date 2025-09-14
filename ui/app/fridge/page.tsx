// app/fridge/page.tsx
'use client';

import { useRef, useState, useEffect } from 'react';

type Mode = 'select' | 'putIn' | 'takeOut';
type FridgeItem = { id: string; name: string; photoUrl: string };

export default function FridgePage() {
  const [mode, setMode] = useState<Mode>('select');
  const [items, setItems] = useState<FridgeItem[]>([]);
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
        videoRef.current!.srcObject = stream;
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
    c.getContext('2d')!.drawImage(v, 0, 0);
    setter(c.toDataURL('image/png'));
  };

  const fetchItems = async () => {
    const res = await fetch('/api/fridge/items');
    setItems(await res.json());
  };

  const handlePutIn = async () => {
    if (!itemPhoto || !userPhoto) return;
    await fetch('/api/fridge/addItem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ itemPhoto, userPhoto }),
    });
    reset();
  };

  const handleTakeOut = async () => {
    if (!selectedItemId || !userPhoto) return;
    await fetch('/api/fridge/removeItem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedItemId, userPhoto }),
    });
    reset();
  };

  const reset = () => {
    setMode('select');
    setSelectedItemId(null);
    setItemPhoto(null);
    setUserPhoto(null);
    setError(null);
  };

  useEffect(() => {
    if (mode === 'takeOut') fetchItems();
  }, [mode]);

  return (
    <main className="max-w-md mx-auto p-6 bg-white rounded-lg shadow-md mt-10 text-gray-800">
      <h1 className="text-2xl font-bold text-center mb-6 text-gray-900">
        Smart Fridge
      </h1>

      {mode === 'select' && (
        <div className="flex justify-center gap-4 mb-6">
          <button
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            onClick={() => setMode('putIn')}
          >
            Put In Item
          </button>
          <button
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            onClick={() => setMode('takeOut')}
          >
            Take Out Item
          </button>
        </div>
      )}

      {(mode === 'putIn' || mode === 'takeOut') && (
        <section>
          <button
            className="text-sm text-gray-600 mb-4 hover:underline"
            onClick={reset}
          >
            ← Back
          </button>

          {mode === 'putIn' && (
            <>
              {/* live preview */}
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full mb-4 rounded border border-gray-300"
              />

              {/* buttons side-by-side */}
              <div className="flex justify-center gap-4 mb-4">
                <button
                  className="px-4 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600"
                  onClick={() => capture(setItemPhoto)}
                >
                  Snap Item
                </button>
                <button
                  className="px-4 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600"
                  onClick={() => capture(setUserPhoto)}
                >
                  Snap Self
                </button>
              </div>

              {/* photos underneath */}
              <div className="flex justify-center gap-4 mb-6">
                {itemPhoto && (
                  <img
                    src={itemPhoto}
                    alt="Item"
                    className="w-1/2 rounded border border-gray-300"
                  />
                )}
                {userPhoto && (
                  <img
                    src={userPhoto}
                    alt="You"
                    className="w-1/2 rounded border border-gray-300"
                  />
                )}
              </div>

              <button
                className="w-full py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-300"
                disabled={!itemPhoto || !userPhoto}
                onClick={handlePutIn}
              >
                Submit Put In
              </button>
            </>
          )}

          {mode === 'takeOut' && (
            <>
              <h2 className="font-semibold mb-2 text-gray-900">
                Select Item to Take Out
              </h2>
              <ul className="mb-4 space-y-2">
                {items.map((it) => (
                  <li key={it.id} className="flex items-center text-gray-900">
                    <input
                      type="radio"
                      name="fridgeItem"
                      value={it.id}
                      onChange={() => setSelectedItemId(it.id)}
                      className="mr-2"
                    />
                    {it.name}
                  </li>
                ))}
              </ul>

              {/* live preview */}
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full mb-4 rounded border border-gray-300"
              />

              {/* Snap Self + photo */}
              <div className="flex flex-col items-center gap-4 mb-6">
                <button
                  className="px-4 py-2 bg-indigo-500 text-white rounded hover:bg-indigo-600"
                  onClick={() => capture(setUserPhoto)}
                >
                  Snap Self
                </button>
                {userPhoto && (
                  <img
                    src={userPhoto}
                    alt="You"
                    className="w-1/2 rounded border border-gray-300"
                  />
                )}
              </div>

              <button
                className="w-full py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:bg-gray-300"
                disabled={!selectedItemId || !userPhoto}
                onClick={handleTakeOut}
              >
                Submit Take Out
              </button>
            </>
          )}

          {error && (
            <p className="mt-4 text-center text-red-600">Error: {error}</p>
          )}
        </section>
      )}

      <canvas ref={canvasRef} className="hidden" />
    </main>
  );
}
