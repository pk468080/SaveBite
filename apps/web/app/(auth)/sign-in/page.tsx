"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { PasswordField } from "@/components/auth/password-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, LoadingState } from "@/components/ui/states";
import { createClient } from "@/lib/supabase/client";
import { signInSchema, type SignInValues } from "@/lib/validation/auth";

/**
 * Sign-in (W3). Supabase Auth is the only identity
 * provider: email + password go to Supabase, the
 * session lives in cookies, and the FastAPI backend
 * receives the access token as a Bearer token. No
 * password is stored by SaveBite itself, and no
 * frontend role is ever trusted for access.
 *
 * The ?next= destination is honoured only when it is
 * a same-site path (starts with one "/" and not with
 * "//"), so an open-redirect cannot be smuggled in.
 */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/customer";
  return raw;
}

function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
  });

  async function onSubmit(values: SignInValues) {
    setError(null);
    setPending(true);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signInWithPassword(values);
      if (authError) {
        setError(authError.message);
        return;
      }
      router.push(next);
      router.refresh();
    } catch {
      setError("Could not sign in. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>Welcome back. Sign in to your SaveBite account.</CardDescription>
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
          <PasswordField
            id="password"
            label="Password"
            autoComplete="current-password"
            error={form.formState.errors.password?.message}
            inputProps={form.register("password")}
          />
          <p className="text-right text-sm">
            <Link href="/forgot-password" className="font-medium text-primary underline-offset-4 hover:underline">
              Forgot password?
            </Link>
          </p>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            New here?{" "}
            <Link href="/sign-up" className="font-medium text-primary underline-offset-4 hover:underline">
              Create an account
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading sign-in…" />}>
      <SignInForm />
    </Suspense>
  );
}
