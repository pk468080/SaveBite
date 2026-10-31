"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { PasswordField } from "@/components/auth/password-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, LoadingState } from "@/components/ui/states";
import { createClient } from "@/lib/supabase/client";
import { z } from "zod";

/**
 * Password reset completion (W3). The reset link from
 * Supabase carries a one-time code; it is exchanged
 * for a short-lived recovery session, then the new
 * password is set through Supabase Auth. If there is
 * no recovery session (expired or already-used link),
 * the form reports that instead of pretending to work.
 */
const schema = z
  .object({
    password: z
      .string()
      .min(8, "Password must be at least 8 characters.")
      .max(72, "Password must be at most 72 characters."),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const [sessionReady, setSessionReady] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const supabase = createClient();
      const code = searchParams.get("code");
      if (code) {
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
        if (!cancelled) setSessionReady(!exchangeError);
        return;
      }
      const { data } = await supabase.auth.getSession();
      if (!cancelled) setSessionReady(Boolean(data.session));
    })();
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  async function onSubmit(values: z.infer<typeof schema>) {
    setError(null);
    setPending(true);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.updateUser({ password: values.password });
      if (authError) {
        setError(authError.message);
        return;
      }
      setDone(true);
    } catch {
      setError("Could not update your password. Please try again.");
    } finally {
      setPending(false);
    }
  }

  if (sessionReady === null) return <LoadingState label="Checking your reset link…" />;

  if (sessionReady === false) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Reset link expired</CardTitle>
          <CardDescription>
            This reset link is invalid or has already been used. Request a new one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (done) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Password updated</CardTitle>
          <CardDescription>Your password has been changed. Sign in with the new one.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/sign-in">Go to sign in</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Choose a new password</CardTitle>
        <CardDescription>At least 8 characters.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          {error ? <Alert variant="error">{error}</Alert> : null}
          <PasswordField
            id="password"
            label="New password"
            autoComplete="new-password"
            error={form.formState.errors.password?.message}
            inputProps={form.register("password")}
          />
          <PasswordField
            id="confirmPassword"
            label="Confirm new password"
            autoComplete="new-password"
            error={form.formState.errors.confirmPassword?.message}
            inputProps={form.register("confirmPassword")}
          />
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? "Updating…" : "Update password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
