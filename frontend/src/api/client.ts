import { API_BASE_URL } from "./config";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type ApiErrorBody = {
  message?: string;
  messages?: string[];
  code?: string;
  details?: unknown;
};

export class ApiError extends Error {
  status: number;
  body?: ApiErrorBody;

  constructor(message: string, status: number, body?: ApiErrorBody) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export type ApiClientConfig = {
  baseUrl?: string;
  defaultHeaders?: Record<string, string>;
  timeoutMs?: number;
  retry?: {
    attempts: number;
    backoffMs: number;
  };
};

const DEFAULT_TIMEOUT_MS = 20000;

const resolveBaseUrl = (override?: string): string => {
  if (override) return override;
  return API_BASE_URL;
};

const buildUrl = (baseUrl: string, path: string): string => {
  if (!baseUrl) return path;
  if (path.startsWith("http")) return path;
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
};

const withTimeout = async <T,>(promise: Promise<T>, timeoutMs: number): Promise<T> => {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new ApiError("Request timed out", 408)), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
};

export type RequestOptions<TBody = unknown> = {
  method?: HttpMethod;
  path: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  body?: TBody;
  signal?: AbortSignal;
};

const buildQuery = (query?: RequestOptions["query"]): string => {
  if (!query) return "";
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    params.set(key, String(value));
  });
  const queryString = params.toString();
  return queryString ? `?${queryString}` : "";
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const withRetry = async <T,>(fn: () => Promise<T>, attempts: number, backoffMs: number): Promise<T> => {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        await sleep(backoffMs * attempt);
      }
    }
  }
  throw lastError;
};

export const createApiClient = (config: ApiClientConfig = {}) => {
  const baseUrl = resolveBaseUrl(config.baseUrl);
  const defaultHeaders = config.defaultHeaders ?? {};
  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const retry = config.retry ?? { attempts: 2, backoffMs: 300 };

  const request = async <TResponse, TBody = unknown>(options: RequestOptions<TBody>): Promise<TResponse> => {
    const method = options.method ?? "GET";
    const url = buildUrl(baseUrl, `${options.path}${buildQuery(options.query)}`);

    const headers: Record<string, string> = {
      Accept: "application/json",
      ...defaultHeaders,
      ...options.headers,
    };

    let body: BodyInit | undefined;
    if (options.body !== undefined && options.body !== null) {
      body = JSON.stringify(options.body);
      headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
    }

    const fetchPromise = fetch(url, {
      method,
      headers,
      body,
      signal: options.signal,
    }).then(async (response) => {
      const contentType = response.headers.get("Content-Type") ?? "";
      const isJson = contentType.includes("application/json");
      const responseBody = isJson ? await response.json().catch(() => undefined) : await response.text();

      if (!response.ok) {
        const message =
          (isJson && (responseBody as ApiErrorBody | undefined)?.message) ||
          response.statusText ||
          "Request failed";
        throw new ApiError(message, response.status, isJson ? (responseBody as ApiErrorBody) : undefined);
      }

      return responseBody as TResponse;
    });

    const execute = () => withTimeout(fetchPromise, timeoutMs);

    return withRetry(execute, retry.attempts, retry.backoffMs);
  };

  return {
    request,
  };
};

export const apiClient = createApiClient();

const trimBom = (value: string) => value.replace(/^\uFEFF/, "");

export const fetchText = async (path: string): Promise<string> => {
  const response = await fetch(path, { headers: { Accept: "text/csv" } });
  if (!response.ok) {
    throw new ApiError(`Failed to fetch ${path}`, response.status);
  }
  return response.text();
};

export const parseCsv = <T>(text: string, mapper: (row: Record<string, string>, index: number) => T): T[] => {
  const rows: string[][] = [];
  let current = "";
  let row: string[] = [];
  let inQuotes = false;

  const flushCell = () => {
    row.push(current);
    current = "";
  };

  const flushRow = () => {
    if (row.length === 1 && row[0] === "") {
      row = [];
      return;
    }
    rows.push(row);
    row = [];
  };

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const nextChar = text[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (!inQuotes && char === ",") {
      flushCell();
      continue;
    }

    if (!inQuotes && (char === "\n" || char === "\r")) {
      if (char === "\r" && nextChar === "\n") {
        i += 1;
      }
      flushCell();
      flushRow();
      continue;
    }

    current += char;
  }

  flushCell();
  flushRow();

  if (rows.length === 0) return [];
  const headers = rows[0].map((header) => trimBom(header).trim());

  return rows.slice(1).map((cells, index) => {
    const record: Record<string, string> = {};
    headers.forEach((header, index) => {
      record[header] = (cells[index] ?? "").trim();
    });
    return mapper(record, index);
  });
};
