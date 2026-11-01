"use client";

import { ApiError, createServices } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

export interface PreferenceCategory {
  key: string;
  label: string;
  description: string;
}

/**
 * Notification preferences (W7). One section shared by the
 * customer and merchant notification pages; each page passes
 * only its own audience's categories.
 *
 * Honesty rules, matching the notification pages: toggles are
 * a draft until Save succeeds — "Saved" appears only after
 * the API confirms — and mandatory categories render locked
 * on with an explanation instead of a working toggle.
 */
export function NotificationPreferencesSection({
  categories,
}: {
  categories: PreferenceCategory[];
}) {
  const [values, setValues] = useState<Record<string, boolean> | null>(null);
  const [mandatory, setMandatory] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const prefs = await createServices(
        createBrowserApiClient(),
      ).notifications.getPreferences();
      const next: Record<string, boolean> = {};
      for (const category of categories) {
        next[category.key] = prefs.preferences[category.key] ?? true;
      }
      setValues(next);
      setMandatory(prefs.mandatory_categories);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not load notification preferences.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (!values) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await createServices(
        createBrowserApiClient(),
      ).notifications.updatePreferences(values);
      const next: Record<string, boolean> = {};
      for (const category of categories) {
        next[category.key] = updated.preferences[category.key] ?? true;
      }
      setValues(next);
      setMandatory(updated.mandatory_categories);
      setSaved(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not save notification preferences.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div>
          <h2 className="text-lg font-semibold">Notification preferences</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Choose which in-app notifications you receive. These settings
            apply only to your account.
          </p>
        </div>
        {error ? <Alert variant="error">{error}</Alert> : null}
        {loading ? (
          <LoadingState label="Loading preferences…" />
        ) : values ? (
          <>
            <div className="flex flex-col gap-3">
              {categories.map((category) => {
                const locked = mandatory.includes(category.key);
                return (
                  <label
                    key={category.key}
                    className="flex items-start gap-3"
                  >
                    <Checkbox
                      aria-label={category.label}
                      checked={values[category.key] ?? true}
                      disabled={locked || saving}
                      onCheckedChange={(checked) =>
                        setValues((current) =>
                          current
                            ? { ...current, [category.key]: checked === true }
                            : current,
                        )
                      }
                    />
                    <span>
                      <span className="font-medium">{category.label}</span>
                      <span className="block text-sm text-muted-foreground">
                        {category.description}
                        {locked ? " Always on." : ""}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="flex items-center gap-3">
              <Button onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save preferences"}
              </Button>
              {saved ? (
                <span className="text-sm text-muted-foreground">
                  Preferences saved.
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <Button variant="outline" onClick={load}>
            Try again
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
