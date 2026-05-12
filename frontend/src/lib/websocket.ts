import type { ConnectionState, RadarPayload } from './types';

export type { ConnectionState };

/** Managed WebSocket wrapper with exponential-backoff reconnection.
 *
 * Does NOT auto-connect on construction — call connect() explicitly.
 * This prevents double connections when React StrictMode double-invokes effects.
 */
export class RadarWebSocket {
  private _ws: WebSocket | null = null;
  private _state: ConnectionState = 'disconnected';
  private _shouldReconnect = false;
  private _reconnectDelay = 1000;

  constructor(
    private readonly _url: string,
    private readonly _onMessage: (payload: RadarPayload) => void,
    private readonly _onStateChange: (state: ConnectionState) => void,
  ) {}

  get state(): ConnectionState {
    return this._state;
  }

  connect(): void {
    this._shouldReconnect = true;
    this._setState('connecting');
    this._ws = new WebSocket(this._url);

    this._ws.onopen = () => {
      this._setState('connected');
      this._reconnectDelay = 1000; // reset backoff on success
    };

    this._ws.onmessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data as string) as RadarPayload;
        this._onMessage(payload);
      } catch (err) {
        console.error('RadarWebSocket: failed to parse message', err);
      }
    };

    this._ws.onerror = () => {
      this._setState('error');
    };

    this._ws.onclose = () => {
      if (this._shouldReconnect) {
        this._setState('connecting');
        setTimeout(() => {
          if (this._shouldReconnect) this.connect();
        }, this._reconnectDelay);
        this._reconnectDelay = Math.min(this._reconnectDelay * 2, 30_000);
      } else {
        this._setState('disconnected');
      }
    };
  }

  disconnect(): void {
    this._shouldReconnect = false; // must be set before close() to suppress reconnect
    this._ws?.close();
    this._ws = null;
  }

  private _setState(s: ConnectionState): void {
    this._state = s;
    this._onStateChange(s);
  }
}
