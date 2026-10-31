"use client";

import { createServices } from "@savebite/api-client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMerchantStores } from "@/components/merchant/store-context";
import { PINCODE_PATTERN, SLUG_PATTERN, validateIndianMobile } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, EmptyState } from "@/components/ui/states";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Create store (W4, M3). Uses exactly the
 * StoreCreate fields. Latitude and longitude are
 * both-or-neither on the backend, slug is
 * lowercased letters/digits/hyphens, pincode is
 * a 6-digit Indian PIN. A new store is NOT
 * active immediately — the page shows the actual
 * status the API returns (draft until admin
 * activation).
 */
export default function NewStorePage() {
  const router = useRouter();
  const { merchants, refresh } = useMerchantStores();
  const [merchantId, setMerchantId] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [addressLine1, setAddressLine1] = useState("");
  const [addressLine2, setAddressLine2] = useState("");
  const [locality, setLocality] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [pickupInstructions, setPickupInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (merchants.length === 0) {
    return (
      <EmptyState
        title="No merchant to attach a store to"
        description="Submit a merchant application first."
      />
    );
  }
  const effectiveMerchantId = merchantId || merchants[0]!.id;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim() || !addressLine1.trim() || !city.trim() || !state.trim()) {
      setError("Store name, address, city and state are required.");
      return;
    }
    const cleanSlug = slug.trim().toLowerCase();
    if (!SLUG_PATTERN.test(cleanSlug)) {
      setError("Slug must use lowercase letters, digits and hyphens only.");
      return;
    }
    if (!PINCODE_PATTERN.test(pincode.trim())) {
      setError("Pincode must be a 6-digit Indian PIN starting with 1–9.");
      return;
    }
    if (contactPhone.trim()) {
      const phoneError = validateIndianMobile(contactPhone.trim());
      if (phoneError) {
        setError(phoneError);
        return;
      }
    }
    const lat = latitude.trim() ? Number(latitude) : null;
    const lng = longitude.trim() ? Number(longitude) : null;
    if ((lat === null) !== (lng === null)) {
      setError("Latitude and longitude must both be given or both be left blank.");
      return;
    }
    if (lat !== null && (Number.isNaN(lat) || lat < -90 || lat > 90)) {
      setError("Latitude must be between -90 and 90.");
      return;
    }
    if (lng !== null && (Number.isNaN(lng) || lng < -180 || lng > 180)) {
      setError("Longitude must be between -180 and 180.");
      return;
    }
    setSubmitting(true);
    try {
      const store = await createServices(createBrowserApiClient()).merchants.createStore(
        effectiveMerchantId,
        {
          name: name.trim(),
          slug: cleanSlug,
          address_line_1: addressLine1.trim(),
          address_line_2: addressLine2.trim() || null,
          locality: locality.trim() || null,
          city: city.trim(),
          state: state.trim(),
          pincode: pincode.trim(),
          latitude: lat,
          longitude: lng,
          contact_phone: contactPhone.trim() || null,
          pickup_instructions: pickupInstructions.trim() || null,
        },
      );
      await refresh();
      router.push(`/merchant/stores/${store.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Store could not be created.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Create a store</h1>
        <p className="text-sm text-muted-foreground">
          Stores are created under one of your merchants. Only merchant owners and admins can
          create stores — the backend enforces that, and a non-owner gets a clear refusal.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Store details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {merchants.length > 1 ? (
              <label className="flex flex-col gap-1 text-sm">
                <span>Merchant *</span>
                <Select value={effectiveMerchantId} onValueChange={setMerchantId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {merchants.map((merchant) => (
                      <SelectItem key={merchant.id} value={merchant.id}>
                        {merchant.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
            ) : null}
            <label className="flex flex-col gap-1 text-sm">
              <span>Store name *</span>
              <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Slug *</span>
              <Input
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
                maxLength={200}
                placeholder="my-store-name"
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Address line 1 *</span>
              <Input value={addressLine1} onChange={(event) => setAddressLine1(event.target.value)} maxLength={500} required />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Address line 2 (optional)</span>
              <Input value={addressLine2} onChange={(event) => setAddressLine2(event.target.value)} maxLength={500} />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm">
                <span>Locality (optional)</span>
                <Input value={locality} onChange={(event) => setLocality(event.target.value)} maxLength={200} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>City *</span>
                <Input value={city} onChange={(event) => setCity(event.target.value)} maxLength={200} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>State *</span>
                <Input value={state} onChange={(event) => setState(event.target.value)} maxLength={200} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Pincode *</span>
                <Input value={pincode} onChange={(event) => setPincode(event.target.value)} maxLength={6} required />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Latitude (optional)</span>
                <Input value={latitude} onChange={(event) => setLatitude(event.target.value)} inputMode="decimal" />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>Longitude (optional)</span>
                <Input value={longitude} onChange={(event) => setLongitude(event.target.value)} inputMode="decimal" />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-sm">
              <span>Contact phone (optional, Indian mobile)</span>
              <Input value={contactPhone} onChange={(event) => setContactPhone(event.target.value)} maxLength={20} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Pickup instructions (optional)</span>
              <Input value={pickupInstructions} onChange={(event) => setPickupInstructions(event.target.value)} maxLength={1000} />
            </label>
            {error ? <Alert variant="error">{error}</Alert> : null}
            <div>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Creating…" : "Create store"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
