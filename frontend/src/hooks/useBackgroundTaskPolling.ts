import { useCallback, useEffect, useRef } from "react";
import { useTaskStore } from "../store";
import { api } from "../api";
import { isTaskRunning } from "../lib/message";

const POLLING_ACTIVE_MS = 5000;
const POLLING_IDLE_MS = 30000;

export function useBackgroundTaskPolling() {
  const { backgroundTasks, setBackgroundTasks } = useTaskStore();
  const hasRunning = backgroundTasks.some((t) => isTaskRunning(t.status));

  const loadBackgroundTasks = useCallback(async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  }, [setBackgroundTasks]);

  const loadRef = useRef(loadBackgroundTasks);
  useEffect(() => {
    loadRef.current = loadBackgroundTasks;
  }, [loadBackgroundTasks]);

  // 只在有进行中的任务且页面可见时轮询
  useEffect(() => {
    let timer: number | undefined;
    const tick = () => {
      loadRef.current().catch(() => undefined);
    };
    const schedule = () => {
      if (timer) window.clearInterval(timer);
      const interval = hasRunning ? POLLING_ACTIVE_MS : POLLING_IDLE_MS;
      timer = window.setInterval(tick, interval);
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        if (timer) window.clearInterval(timer);
        timer = undefined;
      } else {
        tick();
        schedule();
      }
    };

    if (!document.hidden) {
      schedule();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      if (timer) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [hasRunning]);

  return { loadBackgroundTasks };
}
