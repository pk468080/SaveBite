"use client";

import { useEffect, useState } from "react";
import { countdownParts, formatDateTime } from "@/lib/order-labels";

/**
 * Live reservation countdown (W3). Driven only by the
 * ABSOLUTE expiry timestamp returned by the backend —
 * never by a frontend "five minutes from now" guess.
 * The remaining time is recomputed from Date.now() on
 * every tick, so a suspended or throttled tab shows
 * the true remaining time when it resumes. The display
 * never extends the reservation: when it reaches zero,
 * the caller re-reads the order from the backend.
 */
export function ReservationCountdown({
  expiresAt,
  onExpire,
}: {
  expiresAt: string;
  onExpire: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const parts = countdownParts(expiresAt, now);

  useEffect(() => {
    if (parts.expired) onExpire();
    // Only the expiry transition matters; onExpire is
    // stable in the caller (useCallback) or the effect
    // would re-fire on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parts.expired]);

  if (parts.expired) {
    return <p role="status" className="text-sm font-medium text-destructive">Reservation time has run out.</p>;
  }

  const urgent = parts.totalSeconds <= 60;
  return (
    <div role="timer" aria-live="off" className="flex flex-col gap-1">
      <p className={`text-2xl font-bold tabular-nums ${urgent ? "text-destructive" : ""}`}>
        {String(parts.minutes).padStart(2, "0")}:{String(parts.seconds).padStart(2, "0")}
      </p>
      <p className="text-sm text-muted-foreground">
        {urgent
          ? "Almost out of time — complete payment now or the reservation will be released."
          : `Reserved until ${formatDateTime(expiresAt)}.`}
      </p>
    </div>
  );
}
