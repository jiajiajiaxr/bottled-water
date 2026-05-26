/** 前端日志模块。
 *
 * 单例模式，内存队列缓冲，批量上报到后端 /api/v1/logs。
 * 页面关闭时通过 sendBeacon 发送剩余日志，避免丢失。
 * 队列上限 200 条，超限丢弃最早的。
 */
export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  module: string;
  message: string;
  data?: unknown;
  url?: string;
  user_agent?: string;
}

class Logger {
  private queue: LogEntry[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly MAX_QUEUE = 200;
  private readonly BATCH_SIZE = 50;
  private readonly FLUSH_INTERVAL = 5000;

  constructor() {
    this.timer = setInterval(() => this.flush(), this.FLUSH_INTERVAL);
    window.addEventListener("beforeunload", () => this.sendBeacon());
  }

  /** 记录一条日志。 */
  log(level: LogLevel, module: string, message: string, data?: unknown) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      module,
      message,
      data: data ?? undefined,
      url: typeof window !== "undefined" ? window.location.href : undefined,
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : undefined,
    };
    this.queue.push(entry);
    if (this.queue.length > this.MAX_QUEUE) {
      this.queue.shift();
    }
    if (this.queue.length >= this.BATCH_SIZE) {
      this.flush();
    }
  }

  debug(module: string, message: string, data?: unknown) {
    this.log("DEBUG", module, message, data);
  }

  info(module: string, message: string, data?: unknown) {
    this.log("INFO", module, message, data);
  }

  warn(module: string, message: string, data?: unknown) {
    this.log("WARN", module, message, data);
  }

  error(module: string, message: string, data?: unknown) {
    this.log("ERROR", module, message, data);
  }

  /** 立即发送队列中的日志（批量）。 */
  private async flush() {
    if (this.queue.length === 0) return;
    const batch = this.queue.splice(0, this.BATCH_SIZE);
    try {
      await fetch("/api/v1/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ logs: batch }),
        keepalive: true,
      });
    } catch {
      // 静默丢弃，避免循环报错或阻塞业务
    }
  }

  /** 页面卸载时通过 sendBeacon 发送剩余日志。 */
  sendBeacon() {
    if (this.queue.length === 0) return;
    const blob = new Blob([JSON.stringify({ logs: this.queue })], {
      type: "application/json",
    });
    navigator.sendBeacon("/api/v1/logs", blob);
    this.queue = [];
  }
}

export const logger = new Logger();
