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
    const lastPage = Math.ceil(first.total / MAX_PAGE_SIZE);
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

  async predictionsInRange(startDate: string, endDate: string): Promise<Prediction[]> {
    const query = `start_date=${startDate}&end_date=${endDate}&page=1&page_size=${MAX_PAGE_SIZE}`;
    return (await request<ListResponse<Prediction>>(`/api/v1/predictions?${query}`)).items;
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
