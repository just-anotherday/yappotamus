export interface WebSocketLike {
  close(): void;
  onopen: ((event: Event) => unknown) | null;
  onmessage: ((event: MessageEvent) => unknown) | null;
  onclose: ((event: CloseEvent) => unknown) | null;
}

export interface ReconnectingWebSocketOptions {
  createSocket: () => WebSocketLike;
  onMessage: (event: MessageEvent) => void;
  onUnauthorized?: () => void;
  baseDelayMs?: number;
  maxDelayMs?: number;
  jitterRatio?: number;
  random?: () => number;
  setTimer?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
}

export class ReconnectingWebSocket {
  private readonly options: ReconnectingWebSocketOptions;
  private socket: WebSocketLike | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private retryAttempt = 0;

  constructor(options: ReconnectingWebSocketOptions) {
    this.options = options;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;

    if (this.reconnectTimer !== null) {
      (this.options.clearTimer || clearTimeout)(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.close();
    }
  }

  private connect(): void {
    if (this.stopped || this.socket || this.reconnectTimer !== null) return;

    let socket: WebSocketLike;
    try {
      socket = this.options.createSocket();
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;
    socket.onopen = () => {
      if (this.stopped || this.socket !== socket) return;
      this.retryAttempt = 0;
    };
    socket.onmessage = (event) => {
      if (!this.stopped && this.socket === socket) {
        this.options.onMessage(event);
      }
    };
    socket.onclose = (event) => {
      if (this.socket !== socket) return;
      this.socket = null;
      if (this.stopped) return;
      if (event.code === 4401) {
        this.stopped = true;
        this.options.onUnauthorized?.();
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer !== null || this.socket) return;

    const baseDelay = this.options.baseDelayMs ?? 1000;
    const maxDelay = this.options.maxDelayMs ?? 30000;
    const jitterRatio = this.options.jitterRatio ?? 0.2;
    const random = this.options.random || Math.random;
    const exponentialDelay = Math.min(
      maxDelay,
      baseDelay * 2 ** this.retryAttempt,
    );
    const jitter = exponentialDelay * jitterRatio * (random() * 2 - 1);
    const delay = Math.min(maxDelay, Math.max(0, exponentialDelay + jitter));
    this.retryAttempt += 1;

    const setTimer = this.options.setTimer || setTimeout;
    this.reconnectTimer = setTimer(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}
