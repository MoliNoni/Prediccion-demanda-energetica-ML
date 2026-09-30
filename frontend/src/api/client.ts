export type ActiveModel = {
  id: string;
  name: string;
  version: string;
  horizon: number;
  is_active: boolean;
  created_at: string;
};

export type Prediction = {
  id: string;
  target_date: string;
  predicted_demand_kwh: number;
  actual_demand_kwh: number | null;
  model_id: string;
  model_name?: string;
  model_version?: string;
  horizon?: number;
  created_at: string;
};

export type Demand = { date: string; demand_kwh: number };
export type ListResponse<T> = { items: T[]; page: number; page_size: number; total: number };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const MAX_PAGE_SIZE = 100;
const MAX_PAGES = 20;

/** Pages needed for `total` items; a missing or invalid total is a single page. */
function totalPages(total: unknown): number {
  if (typeof total !== "number" || !Number.isFinite(total) || total < 1) return 1;
  return Math.ceil(total / MAX_PAGE_SIZE);
}

/** Pages to read when loading a whole range, capped at MAX_PAGES. */
function cappedPageCount(total: unknown): number {
  const pages = totalPages(total);
  if (pages > MAX_PAGES) {
    console.warn(`Predictions span ${pages} pages; only the first ${MAX_PAGES} are loaded.`);
    return MAX_PAGES;
  }
  return pages;
}

/** status 0 means the request never reached the server. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError("Network error", 0);
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Request failed (${response.status})`, response.status);
  }
  return payload as T;
}

export const api = {
  health: () => request<{ status: "ok" }>("/health"),
  activeModel: () => request<ActiveModel>("/api/v1/models/active"),

  /** The API sorts ascending by target date, so the most recent items live on the last page. */
  async recentPredictions(): Promise<{ items: Prediction[]; total: number }> {
    const first = await request<ListResponse<Prediction>>(`/api/v1/predictions?page=1&page_size=${MAX_PAGE_SIZE}`);
    // The most recent rows are on the true last page, so this path must never be capped.
    const lastPage = totalPages(first.total);
    if (lastPage <= 1) return { items: first.items, total: first.total };
    // A short last page would leave the ledger nearly empty, so include the previous full page.
    const pages = lastPage === 2 ? [2] : [lastPage - 1, lastPage];
    const responses = await Promise.all(
      pages.map((page) => request<ListResponse<Prediction>>(`/api/v1/predictions?page=${page}&page_size=${MAX_PAGE_SIZE}`)),
    );
    const earlier = lastPage === 2 ? first.items : [];
    return { items: [...earlier, ...responses.flatMap((response) => response.items)], total: first.total };
  },

  /** The newest generated predictions, ordered by the server so old target dates cannot hide them. */
  async newestPredictions(pageSize: number): Promise<Prediction[]> {
    const query = `order=created_desc&page=1&page_size=${pageSize}`;
    return (await request<ListResponse<Prediction>>(`/api/v1/predictions?${query}`)).items;
  },

  /** Every prediction in the range, all models included; pages are read until the reported total is reached. */
  async predictionsInRange(startDate: string, endDate: string): Promise<Prediction[]> {
    const pageQuery = (page: number) =>
      `/api/v1/predictions?start_date=${startDate}&end_date=${endDate}&page=${page}&page_size=${MAX_PAGE_SIZE}`;
    const first = await request<ListResponse<Prediction>>(pageQuery(1));
    const lastPage = cappedPageCount(first.total);
    if (lastPage <= 1) return first.items;
    // A rejected later page rejects the whole call so the caller's error path runs (no silent partial list).
    const rest = await Promise.all(
      Array.from({ length: lastPage - 1 }, (_, index) => request<ListResponse<Prediction>>(pageQuery(index + 2))),
    );
    return [...first.items, ...rest.flatMap((response) => response.items)];
  },

  async demandInRange(startDate: string, endDate: string): Promise<Demand[]> {
    const query = `start_date=${startDate}&end_date=${endDate}&page=1&page_size=${MAX_PAGE_SIZE}`;
    return (await request<ListResponse<Demand>>(`/api/v1/demand?${query}`)).items;
  },

  createPrediction: (targetDate: string) =>
    request<Prediction>("/api/v1/predictions", {
      method: "POST",
      body: JSON.stringify({ target_date: targetDate }),
    }),
};
