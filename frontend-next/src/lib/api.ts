const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "";

export { WS_BASE };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export function getLoginUrl() {
  return `${API_BASE}/api/auth/login`;
}

export function fetchMe() {
  return request<{
    id: number;
    github_id: number;
    login: string;
    name: string | null;
    email: string | null;
    avatar_url: string | null;
  }>("/api/auth/me");
}

export function logout() {
  return request<{ status: string }>("/api/auth/logout", { method: "POST" });
}

// ── Repos ─────────────────────────────────────────────────────────────────────

export interface WikiStructurePage {
  id: string;
  title: string;
  parent_id: string | null;
  dir_path: string;
}

export interface Repo {
  id: number;
  owner: string;
  name: string;
  url: string;
  description: string | null;
  language: string | null;
  is_private: boolean;
  last_commit_sha: string | null;
  indexed_at: string | null;
  index_status: "pending" | "indexing" | "ready" | "stale" | "failed";
  chunk_count: number;
  file_count: number;
  error_message: string | null;
  wiki_structure: WikiStructurePage[];
  dependencies: string[];
  created_at: string | null;
  updated_at: string | null;
}

export function ingestRepo(url: string) {
  return request<{ job_id: string | null; status: string; repo_id: number; message?: string }>(
    "/api/repos/ingest",
    { method: "POST", body: JSON.stringify({ url }) }
  );
}

export function listRepos() {
  return request<Repo[]>("/api/repos");
}

export function getRepo(id: number) {
  return request<Repo>(`/api/repos/${id}`);
}

export function deleteRepo(id: number) {
  return request<{ status: string }>(`/api/repos/${id}`, { method: "DELETE" });
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export interface Job {
  id: string;
  repo_id: number;
  status: "pending" | "running" | "completed" | "failed";
  progress_step: string | null;
  progress_pct: number;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export function getJob(jobId: string) {
  return request<Job>(`/api/jobs/${jobId}`);
}

/** SSE URL for real-time job progress — use with EventSource */
export function jobStreamUrl(jobId: string) {
  return `${API_BASE}/api/jobs/${jobId}/stream`;
}

// ── Wiki ──────────────────────────────────────────────────────────────────────

export interface WikiPageMeta {
  path: string;
  title: string;
  generated_at: string | null;
  has_content: boolean;
}

export interface WikiPageFull {
  id: number;
  repo_id: number;
  path: string;
  title: string;
  content_md: string | null;
  mermaid_diagram: string | null;
  generated_at: string | null;
  generating: boolean;
}

export function listWikiPages(repoId: number) {
  return request<{ pages: WikiPageMeta[]; available_dirs: string[] }>(
    `/api/wiki/${repoId}/pages`
  );
}

export function getWikiPage(repoId: number, path: string) {
  return request<WikiPageFull>(`/api/wiki/${repoId}/pages/${path}`);
}
