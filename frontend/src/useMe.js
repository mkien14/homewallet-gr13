import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useMe() {
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(
    () => api("/api/me").then((result) => { setMe(result); setError(null); }).catch((e) => setError(e.message)),
    []
  );
  const clearHousehold = useCallback(() => {
    setMe((current) => current ? { ...current, household: null } : current);
    setError(null);
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  return { me, error, reload, clearHousehold };
}
