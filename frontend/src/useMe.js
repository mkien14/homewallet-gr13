import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useMe() {
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(
    () => api("/api/me").then(setMe).catch((e) => setError(e.message)),
    []
  );
  useEffect(() => {
    reload();
  }, [reload]);

  return { me, error, reload };
}