import { useEffect, useRef, useState, useCallback } from "react";

export type SimParams = Record<string, number | string | boolean>;
export type SimResult = Record<string, unknown>;

type PendingResolvers = Map<number, { resolve: (r: SimResult) => void; reject: (e: Error) => void }>;

// Encapsula el ciclo de vida del Web Worker que corre Pyodide + el motor
// Python real (engine/simulator.py). La UI de React nunca bloquea: init()
// descarga Pyodide/numpy/pandas/scipy una sola vez, run() reutiliza esa
// instancia para cada simulacion.
export function usePyodideWorker() {
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<PendingResolvers>(new Map());
  const nextIdRef = useRef(0);
  const [status, setStatus] = useState("Iniciando…");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const worker = new Worker(new URL("../worker/pyodideWorker.js", import.meta.url));
    workerRef.current = worker;

    worker.onmessage = (event: MessageEvent) => {
      const msg = event.data;
      if (msg.type === "status") {
        setStatus(msg.message);
      } else if (msg.type === "ready") {
        setStatus("Motor listo.");
        setReady(true);
      } else if (msg.type === "result") {
        const pending = pendingRef.current.get(msg.id);
        if (pending) {
          pending.resolve(msg.result);
          pendingRef.current.delete(msg.id);
        }
      } else if (msg.type === "error") {
        if (msg.id != null && pendingRef.current.has(msg.id)) {
          pendingRef.current.get(msg.id)!.reject(new Error(msg.message));
          pendingRef.current.delete(msg.id);
        } else {
          setError(msg.message);
        }
      }
    };

    // BASE_URL refleja el `base` de vite.config.ts (relativo, './'); se
    // resuelve a absoluto aqui (en el hilo principal, donde window.location
    // esta bien definido) para que el worker pueda hacer fetch() de los
    // .py sin depender de la ubicacion del propio script del worker tras
    // el bundling de produccion.
    const baseUrl = new URL(import.meta.env.BASE_URL, window.location.href).href;

    worker.postMessage({ type: "init", baseUrl });

    return () => worker.terminate();
  }, []);

  const run = useCallback((params: SimParams): Promise<SimResult> => {
    return new Promise((resolve, reject) => {
      const worker = workerRef.current;
      if (!worker) { reject(new Error("Worker no inicializado")); return; }
      const id = nextIdRef.current++;
      pendingRef.current.set(id, { resolve, reject });
      worker.postMessage({ type: "run", id, params });
    });
  }, []);

  return { status, ready, error, run };
}
