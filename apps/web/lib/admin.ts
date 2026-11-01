/**
 * Admin display labels (W6). These only label
 * values the backend returns; they never decide
 * access, and no label invents a status the
 * backend does not have.
 */

export function merchantStatusLabel(status: string): string {
  switch (status) {
    case "pending_review":
      return "Pending review";
    case "additional_information_required":
      return "Needs more information";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "suspended":
      return "Suspended";
    default:
      return status;
  }
}

export function merchantVerificationLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Verification pending";
    case "under_review":
      return "Verification under review";
    case "verified":
      return "Verified";
    case "rejected":
      return "Verification rejected";
    case "expired":
      return "Verification expired";
    default:
      return status;
  }
}

export function storeStatusLabel(status: string): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "active":
      return "Active";
    case "inactive":
      return "Inactive";
    case "suspended":
      return "Suspended";
    default:
      return status;
  }
}

export function moderationStatusLabel(status: string): string {
  switch (status) {
    case "visible":
      return "Visible";
    case "hidden":
      return "Hidden";
    case "under_review":
      return "Under review";
    default:
      return status;
  }
}

/** Page size used by every admin list (backend default is 20). */
export const ADMIN_PAGE_SIZE = 20;
