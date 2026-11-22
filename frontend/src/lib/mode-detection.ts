/**
 * Startup-only Operating Mode detection/fallback (Dashboard_Frontend_Architecture.md:84,99,109 —
 * "mode detection/fallback" is named as `lib/`'s responsibility; Operating Mode's documented
 * persistence is "None, re-detected per session" with reset behavior "Only at startup fallback").
 *
 * Attempts one short, bounded reachability check against the live backend. If it responds, the
 * session runs in Mode A; otherwise it falls back to the build's default demonstration mode. This
 * never re-checks mid-session — matching the frozen "re-detected per session" / "startup fallback"
 * contract, not continuous polling.
 */
import { BACKEND_URL } from "./backend-adapter"

const DETECTION_TIMEOUT_MS = 1500

export async function detectLiveBackend(): Promise<boolean> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), DETECTION_TIMEOUT_MS)
  try {
    const response = await fetch(`${BACKEND_URL}/observation-records`, {
      method: "GET",
      signal: controller.signal,
    })
    return response.ok
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}
