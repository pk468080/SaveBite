"use client";

import Link from "next/link";
import { Menu, ShoppingBag, X } from "lucide-react";
import { useState } from "react";
import { SignOutButton } from "@/components/shared/sign-out-button";
import { useCart } from "@/components/cart/cart-context";

/** SaveBite brand treatment: text + icon only. No
 * official logo exists in the repository, and none is
 * invented here. */
export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 font-bold text-lg" aria-label="SaveBite home">
      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <ShoppingBag className="h-5 w-5" aria-hidden="true" />
      </span>
      SaveBite
    </Link>
  );
}

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/marketplace", label: "Explore Food" },
  { href: "/#how-it-works", label: "How It Works" },
  { href: "/#about", label: "About" },
];

/**
 * Public header. `authenticated` comes from the server
 * layout (real Supabase session), so signed-in visitors
 * see an account entry point instead of Sign in / Get
 * Started. Mobile navigation is a disclosure toggle,
 * keyboard accessible.
 */
export function SiteHeader({ authenticated }: { authenticated: boolean }) {
  const [open, setOpen] = useState(false);
  // CartProvider wraps the whole app at the root layout;
  // the badge is a convenience only and never a reservation.
  const cartCount = useCart().itemCount;
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <Brand />
        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <Link href="/cart" className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
            Cart{cartCount > 0 ? ` (${cartCount})` : ""}
          </Link>
          {authenticated ? (
            <>
              <Link href="/customer" className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
                My account
              </Link>
              <SignOutButton />
            </>
          ) : (
            <>
              <Link href="/sign-in" className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
                Sign In
              </Link>
              <Link
                href="/sign-up"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
              >
                Get Started
              </Link>
            </>
          )}
        </div>
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent md:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close navigation menu" : "Open navigation menu"}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
        </button>
      </div>
      {open ? (
        <nav id="mobile-nav" aria-label="Mobile" className="border-t px-4 py-3 md:hidden">
          <ul className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="block rounded-md px-3 py-2 text-sm font-medium hover:bg-accent"
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link href="/cart" className="block rounded-md px-3 py-2 text-sm font-medium hover:bg-accent" onClick={() => setOpen(false)}>
                Cart{cartCount > 0 ? ` (${cartCount})` : ""}
              </Link>
            </li>
            {authenticated ? (
              <li>
                <Link href="/customer" className="block rounded-md px-3 py-2 text-sm font-medium hover:bg-accent" onClick={() => setOpen(false)}>
                  My account
                </Link>
              </li>
            ) : (
              <>
                <li>
                  <Link href="/sign-in" className="block rounded-md px-3 py-2 text-sm font-medium hover:bg-accent" onClick={() => setOpen(false)}>
                    Sign In
                  </Link>
                </li>
                <li>
                  <Link href="/sign-up" className="block rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground" onClick={() => setOpen(false)}>
                    Get Started
                  </Link>
                </li>
              </>
            )}
          </ul>
        </nav>
      ) : null}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm sm:grid-cols-3 sm:px-6">
        <div>
          <h2 className="mb-3 font-semibold text-foreground">About SaveBite</h2>
          <p className="text-muted-foreground">
            Good food. Better prices. Less waste. SaveBite connects you with
            surplus food from local stores — collected at the store, never
            delivered.
          </p>
        </div>
        <nav aria-label="Footer explore">
          <h2 className="mb-3 font-semibold text-foreground">Explore</h2>
          <ul className="flex flex-col gap-2 text-muted-foreground">
            <li><Link href="/marketplace" className="hover:text-foreground">Explore Food</Link></li>
            <li><Link href="/#how-it-works" className="hover:text-foreground">How It Works</Link></li>
            <li><Link href="/#about" className="hover:text-foreground">About SaveBite</Link></li>
          </ul>
        </nav>
        <nav aria-label="Footer account">
          <h2 className="mb-3 font-semibold text-foreground">Get started</h2>
          <ul className="flex flex-col gap-2 text-muted-foreground">
            <li><Link href="/sign-in" className="hover:text-foreground">Sign In</Link></li>
            <li><Link href="/sign-up" className="hover:text-foreground">Create an account</Link></li>
            <li><Link href="/merchant" className="hover:text-foreground">Sell surplus food (merchants)</Link></li>
          </ul>
          <p className="mt-3 text-muted-foreground">
            No contact, terms, or privacy pages exist yet — links to them
            are deliberately omitted rather than fabricated.
          </p>
        </nav>
      </div>
    </footer>
  );
}
