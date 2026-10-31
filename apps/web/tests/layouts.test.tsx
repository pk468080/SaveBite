import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());
import { AppNav } from "@/components/shared/app-nav";
import { SiteHeader } from "@/components/shared/site-header";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/states";

// Next.js navigation is mocked: pathname is /customer/orders.
vi.mock("next/navigation", () => ({
  usePathname: () => "/customer/orders",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("public layout", () => {
  it("renders brand, marketplace link, and sign-in entry", () => {
    render(<SiteHeader />);
    expect(screen.getByLabelText("SaveBite home")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marketplace" })).toHaveAttribute(
      "href",
      "/marketplace",
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });
});

describe("app navigation", () => {
  it("marks the current section and keeps other links reachable", () => {
    render(
      <AppNav
        title="Customer"
        items={[
          { href: "/customer", label: "Overview" },
          { href: "/customer/orders", label: "My orders" },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "My orders" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });
});

describe("shared states", () => {
  it("renders button, empty state, and error state accessibly", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    render(<EmptyState title="Nothing here yet" description="Try again later." />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
    render(<ErrorState />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
