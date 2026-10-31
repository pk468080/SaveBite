"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/states";
import { config } from "@/lib/config";
import { createClient } from "@/lib/supabase/client";

/**
 * Password recovery (W3). Supabase Auth's built-in
 * recovery flow: an email with a reset link is sent,
 * and /reset-password completes it. No reset code or
 * password ever passes through SaveBite's own backend.
 * The confirmation message is deliberately generic so
 * it does not reveal whether an address has an account.
 */
const schema = z.object({
  email: z.string().email("Enter a valid email address."),
});

export default function ForgotPasswordPage() {
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });

  async function onSubmit(values: z.infer<typeof schema>) {
    setError(null);
    setPending(true);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.resetPasswordForEmail(values.email, {
        redirectTo: `${config.siteUrl}/reset-password`,
      });
      if (authError) {
        setError(authError.message);
        return;
      }
      setDone(true);
    } catch {
      setError("Could not send the reset email. Please try again.");
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Check your email</CardTitle>
          <CardDescription>
            If an account exists for that address, a password-reset link is on its way.
            The link expires, so use it soon.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/sign-in">Back to sign in</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Forgot password?</CardTitle>
        <CardDescription>Enter your email and we will send you a reset link.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          {error ? <Alert variant="error">{error}</Alert> : null}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
            {form.formState.errors.email ? (
              <p role="alert" className="text-sm text-destructive">
                {form.formState.errors.email.message}
              </p>
            ) : null}
          </div>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? "Sending…" : "Send reset link"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Remembered it?{" "}
            <Link href="/sign-in" className="font-medium text-primary underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
