/**
 * Backwards-compatible re-exports for the old combined
 * module. Importing this file from a CLIENT component
 * pulls in next/headers and fails the production build,
 * so new code must import from lib/api/browser.ts
 * (client) or lib/api/server.ts (server) directly.
 * Kept only so existing server imports keep working
 * until they are migrated.
 */
export { createBrowserApiClient } from "@/lib/api/browser";
export { createServerApiClient } from "@/lib/api/server";
