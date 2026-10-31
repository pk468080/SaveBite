import Link from "next/link";
import { ShoppingBag } from "lucide-react";

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

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <Brand />
        <nav aria-label="Main" className="flex items-center gap-1 sm:gap-2">
          <Link href="/marketplace" className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
            Marketplace
          </Link>
          <Link href="/customer" className="hidden rounded-md px-3 py-2 text-sm font-medium hover:bg-accent sm:block">
            My orders
          </Link>
          <Link href="/sign-in" className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent">
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          >
            Sign up
          </Link>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>SaveBite — good food, rescued before it goes to waste.</p>
        <nav aria-label="Footer" className="flex gap-4">
          <Link href="/marketplace" className="hover:text-foreground">Marketplace</Link>
          <Link href="/merchant" className="hover:text-foreground">For businesses</Link>
          <Link href="/admin" className="hover:text-foreground">Platform admin</Link>
        </nav>
      </div>
    </footer>
  );
}
