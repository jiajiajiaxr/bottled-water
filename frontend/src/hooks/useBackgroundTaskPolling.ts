import { useCallback, useEffect, useRef } from "react";
import { useTaskStore } from "../store";
import { api } from "../api";

export function useBackgroundTaskPolling(intervalMs = 3500) {
  const { setBackgroundTasks } = useTaskStore();

  const loadBackgroundTasks = useCallback(async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  }, [setBackgroundTasks]);

  const loadRef = useRef(loadBackgroundTasks);
  useEffect(() => {
    loadRef.current = loadBackgroundTasks;
  }, [loadBackgroundTasks]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadRef.current().catch(() => undefined);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);

  return { loadBackgroundTasks };
}
