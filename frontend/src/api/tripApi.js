const BASE_URL = "http://127.0.0.1:8000/api";

/**
 * Flatten a DRF validation error detail object into a single readable string.
 * e.g. { current_cycle_used_hours: ["Ensure this value is..."] }
 *   → "Current cycle used hours: Ensure this value is..."
 */
function flattenDetail(detail) {
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail.join(" ");
  }

  if (typeof detail === "object" && detail !== null) {
    return Object.entries(detail)
      .map(([field, msgs]) => {
        const label = field
          .replace(/_/g, " ")
          .replace(/\b\w/g, (c) => c.toUpperCase());
        const text = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
        return `${label}: ${text}`;
      })
      .join(" ");
  }

  return "Request failed";
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    // Network-level failure (API offline, CORS, etc.)
    throw Object.assign(
      new Error("Unable to reach the planning server. Check that the API is running."),
      { status: 0 }
    );
  }

  const data = await res.json();
  if (!res.ok) {
    const message = flattenDetail(data?.detail) || "Request failed";
    throw Object.assign(new Error(message), { status: res.status });
  }
  return data;
}

export const tripApi = {
  healthCheck: () => request("/health/"),
  planTrip: (payload) =>
    request("/trips/plan/", { method: "POST", body: JSON.stringify(payload) }),
  getTrip: (id) => request(`/trips/${id}/`),
  listTrips: () => request("/trips/"),
  getRoute: (payload) =>
    request("/route/", { method: "POST", body: JSON.stringify(payload) }),
};
