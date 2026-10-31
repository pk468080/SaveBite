"use client";

import { createServices, type StoreHoursEntry } from "@savebite/api-client";
import { use, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Store hours editor (W4, M3). Weekdays are the
 * backend integers 0-6. The repository states
 * nowhere whether 0 is Monday or Sunday, so the
 * editor shows the number and says so plainly —
 * it never guesses day names. Closed days carry
 * no times; open days need opens_at before
 * closes_at. Hours access is owner/admin or a
 * store_manager with an active merchant
 * membership; anyone else gets the backend
 * refusal, not a silent empty form.
 */
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

function emptyHours(): StoreHoursEntry[] {
  return WEEKDAYS.map((weekday) => ({ weekday, is_closed: true, opens_at: null, closes_at: null }));
}

export default function StoreHoursPage({ params }: { params: Promise<{ storeId: string }> }) {
  const { storeId } = use(params);
  const [hours, setHours] = useState<StoreHoursEntry[]>(emptyHours());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    createServices(createBrowserApiClient())
      .merchants.getStoreHours(storeId)
      .then((data) => {
        if (cancelled) return;
        const byDay = new Map(data.hours.map((entry) => [entry.weekday, entry]));
        setHours(WEEKDAYS.map((weekday) => byDay.get(weekday) ?? { weekday, is_closed: true, opens_at: null, closes_at: null }));
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  function update(weekday: number, patch: Partial<StoreHoursEntry>) {
    setHours((current) =>
      current.map((entry) => (entry.weekday === weekday ? { ...entry, ...patch } : entry)),
    );
  }

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(false);
    for (const entry of hours) {
      if (entry.is_closed) {
        if (entry.opens_at || entry.closes_at) {
          setError(`Weekday ${entry.weekday}: a closed day must not have opening or closing times.`);
          return;
        }
      } else {
        if (!entry.opens_at || !entry.closes_at) {
          setError(`Weekday ${entry.weekday}: an open day needs both opening and closing times.`);
          return;
        }
        if (entry.opens_at >= entry.closes_at) {
          setError(`Weekday ${entry.weekday}: opening time must be before closing time.`);
          return;
        }
      }
    }
    setSaving(true);
    try {
      const result = await createServices(createBrowserApiClient()).merchants.updateStoreHours(
        storeId,
        hours.map((entry) => ({
          weekday: entry.weekday,
          is_closed: entry.is_closed,
          opens_at: entry.is_closed ? null : entry.opens_at,
          closes_at: entry.is_closed ? null : entry.closes_at,
        })),
      );
      const byDay = new Map(result.hours.map((entry) => [entry.weekday, entry]));
      setHours(WEEKDAYS.map((weekday) => byDay.get(weekday) ?? { weekday, is_closed: true, opens_at: null, closes_at: null }));
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hours could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState label="Loading hours" />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Store hours</h1>
        <p className="text-sm text-muted-foreground">
          Weekly schedule, stored as weekday numbers 0–6. The backend does not confirm whether 0
          means Monday or Sunday, so day names are deliberately not shown here — after saving,
          check the hours shown for this store before relying on them for a live day.
        </p>
      </div>
      <form onSubmit={handleSave}>
        <Card>
          <CardHeader>
            <CardTitle>Weekly hours</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {hours.map((entry) => (
              <div key={entry.weekday} className="flex flex-wrap items-center gap-3 text-sm">
                <span className="w-24 font-medium">Weekday {entry.weekday}</span>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={entry.is_closed}
                    onChange={(event) =>
                      update(entry.weekday, {
                        is_closed: event.target.checked,
                        opens_at: event.target.checked ? null : (entry.opens_at ?? "09:00"),
                        closes_at: event.target.checked ? null : (entry.closes_at ?? "21:00"),
                      })
                    }
                  />
                  Closed
                </label>
                {!entry.is_closed ? (
                  <>
                    <label className="flex items-center gap-1">
                      Opens
                      <Input
                        type="time"
                        className="w-32"
                        value={entry.opens_at ?? ""}
                        onChange={(event) => update(entry.weekday, { opens_at: event.target.value || null })}
                        required
                      />
                    </label>
                    <label className="flex items-center gap-1">
                      Closes
                      <Input
                        type="time"
                        className="w-32"
                        value={entry.closes_at ?? ""}
                        onChange={(event) => update(entry.weekday, { closes_at: event.target.value || null })}
                        required
                      />
                    </label>
                  </>
                ) : null}
              </div>
            ))}
            {error ? <Alert variant="error">{error}</Alert> : null}
            {success ? <Alert variant="success">Hours saved.</Alert> : null}
            <div>
              <Button type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save hours"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
