let tick = 0;

function emit(event, detail = {}) {
  process.stdout.write(
    JSON.stringify({
      event,
      detail,
      at: new Date().toISOString(),
    }) + "\n",
  );
}

emit("agent.started", {
  mode: "local-supervisor",
  capabilities: ["workspace-watch", "task-heartbeat", "safe-notify"],
});

const timer = setInterval(() => {
  tick += 1;
  emit("agent.heartbeat", {
    tick,
    cpu_slot: "reserved",
    queue_depth: Math.max(0, 3 - (tick % 4)),
  });
}, 5000);

function shutdown(signal) {
  clearInterval(timer);
  emit("agent.stopped", { signal });
  process.exit(0);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
