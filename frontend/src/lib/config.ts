const DEV_API_BASE = "http://localhost:8000";
const DEFAULT_WS_PATH = "/ws/radar";

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function deriveWsUrl(apiBase: string, wsPath: string): string {
  const normalizedApi = trimTrailingSlash(apiBase);
  const path = wsPath.startsWith("/") ? wsPath : `/${wsPath}`;
  if (normalizedApi.startsWith("https://")) {
    return `${normalizedApi.replace("https://", "wss://")}${path}`;
  }
  if (normalizedApi.startsWith("http://")) {
    return `${normalizedApi.replace("http://", "ws://")}${path}`;
  }
  return `${normalizedApi}${path}`;
}

function defaultApiBase(): string {
  if (typeof window !== "undefined" && window.location) {
    // When served by the same FastAPI process (production deploys, including
    // OSC), the API lives on the same origin as the SPA. Falling back to
    // window.location.origin keeps the bundle URL-agnostic.
    return window.location.origin;
  }
  return DEV_API_BASE;
}

export const API_BASE = trimTrailingSlash(
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
    defaultApiBase(),
);

export const WS_URL =
  (import.meta.env.VITE_WS_URL as string | undefined)?.trim() ||
  deriveWsUrl(API_BASE, DEFAULT_WS_PATH);
