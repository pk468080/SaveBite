"use client";

import { createServices, type MerchantBusinessTypeValue } from "@savebite/api-client";
import Link from "next/link";
import { useState } from "react";
import { BUSINESS_TYPES, businessTypeLabel, validateIndianMobile } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/states";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createBrowserApiClient } from "@/lib/api/browser";
import { useMerchantStores } from "@/components/merchant/store-context";

/**
 * Merchant onboarding (W4, M3). Submits exactly
 * the fields POST /v1/merchants/applications
 * accepts: legal name, display name, business
 * type, optional business email and phone. Email
 * and phone are optional in the database — the
 * form does not invent a stricter requirement.
 * Approval is an admin action; this page never
 * claims an application is approved, and document
 * submission has no merchant-facing endpoint yet
 * (see /merchant/application for that notice).
 */
export default function MerchantOnboardingPage() {
  const { refresh } = useMerchantStores();
  const [legalName, setLegalName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [businessType, setBusinessType] = useState<MerchantBusinessTypeValue>("restaurant");
  const [businessEmail, setBusinessEmail] = useState("");
  const [businessPhone, setBusinessPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!legalName.trim() || !displayName.trim()) {
      setError("Legal business name and display name are both required.");
      return;
    }
    if (businessEmail.trim()) {
      const email = businessEmail.trim();
      if (!email.includes("@") || email.includes(" ") || email.split("@").length !== 2) {
        setError("Enter a valid business email, or leave it blank.");
        return;
      }
    }
    if (businessPhone.trim()) {
      const phoneError = validateIndianMobile(businessPhone.trim());
      if (phoneError) {
        setError(phoneError);
        return;
      }
    }
    setSubmitting(true);
    try {
      await createServices(createBrowserApiClient()).merchants.submitApplication({
        legal_name: legalName.trim(),
        display_name: displayName.trim(),
        business_type: businessType,
        business_email: businessEmail.trim() || null,
        business_phone: businessPhone.trim() || null,
      });
      setSuccess(true);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Application could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Application submitted</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Your application is now pending review. Approval is done by the SaveBite team, not here
            — this page cannot approve it. You can follow its real status on the application page.
          </p>
          <div>
            <Button asChild>
              <Link href="/merchant/application">View application status</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Merchant onboarding</h1>
        <p className="text-sm text-muted-foreground">
          Tell SaveBite about your business so it can be reviewed. Your business information is
          used to verify who you are before any store can go live.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Business application</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm">
              <span>Legal business name *</span>
              <Input
                value={legalName}
                onChange={(event) => setLegalName(event.target.value)}
                maxLength={200}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Display name *</span>
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={200}
                required
              />
              <span className="text-xs text-muted-foreground">
                The name customers see for your business.
              </span>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Business type *</span>
              <Select
                value={businessType}
                onValueChange={(value) => setBusinessType(value as MerchantBusinessTypeValue)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BUSINESS_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {businessTypeLabel(type)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Business email (optional)</span>
              <Input
                type="email"
                value={businessEmail}
                onChange={(event) => setBusinessEmail(event.target.value)}
                maxLength={254}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span>Business phone (optional, Indian mobile)</span>
              <Input
                value={businessPhone}
                onChange={(event) => setBusinessPhone(event.target.value)}
                maxLength={20}
                placeholder="9876543210 or +91 9876543210"
              />
            </label>
            {error ? <Alert variant="error">{error}</Alert> : null}
            <div>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Submitting…" : "Submit application"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
