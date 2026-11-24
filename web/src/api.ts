// Types mirror api/schemas.py. Keep them in sync when the API changes.

export type Factor = { label: string; detail: string };

export type Ward = {
  ward_id: number;
  ward_name: string;
  priority_rank: number;
  score: number;
  level: "High" | "Medium" | "Low";
  top_factors: Factor[];
  failure_rank: number;
  low_report_rank: number;
  subsidy_participation: number;
  eligible_homes: number;
  properties_without_fpd: number;
  flood_reports_2019_2022: number;
};

export type AskedWard = {
  ward_id: number;
  ward_name: string;
  priority_rank: number;
  failure_rank: number;
  low_report_rank: number;
  subsidy_participation: number;
  properties_with_fpd: number;
  properties_without_fpd: number;
  flood_reports_2019_2022: number;
  topic_rank: number | null;
  topic_value: string | null;
};

export type Excerpt = {
  source: string;
  page: number;
  ward_id: number | null;
  score: number;
  text: string;
};

export type AskResponse = {
  message_id: string;
  question: string;
  kind: "program" | "wards" | "both" | "unknown";
  topic_label: string | null;
  basis: string;
  wards: AskedWard[];
  passages: Excerpt[];
  help: string | null;
  model: string;
  answer: string | null;
  llm_available: boolean | null;
};

async function fail(res: Response): Promise<never> {
  let detail = `The server answered ${res.status}.`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
  } catch {
    /* body was not JSON */
  }
  throw new Error(detail);
}

const LOCAL_ONLY =
  "This page shows the ward map. Questions run on your computer: python -m uvicorn api.main:app";

export async function getWards(): Promise<Ward[]> {
  try {
    const res = await fetch("/api/wards");
    if (res.ok) return res.json();
  } catch {
    /* published site has no API; use the snapshot written at build time */
  }
  const res = await fetch(`${import.meta.env.BASE_URL}wards.json`);
  if (!res.ok) return fail(res);
  return res.json();
}

// Written by "311 service request/Dashboard/build_flood_requests_json.py".
// wards[id][yearIndex][seasonIndex][typeIndex] is a count of finished requests.
export type FloodRequests = {
  source: string;
  filter: string;
  through: string;
  years: number[];
  seasons: string[];
  types: string[];
  total: number;
  wards: Record<string, number[][][]>;
};

export async function getFloodRequests(): Promise<FloodRequests> {
  const res = await fetch(`${import.meta.env.BASE_URL}flood_requests.json`);
  if (!res.ok) return fail(res);
  // A missing file can come back as the page itself, so check before parsing.
  if (!(res.headers.get("content-type") ?? "").includes("json")) {
    throw new Error("The flooding-request data is missing. Run build_flood_requests_json.py.");
  }
  return res.json();
}

export async function ask(question: string, model: string): Promise<AskResponse> {
  let res: Response;
  try {
    res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, model }),
    });
  } catch {
    throw new Error(LOCAL_ONLY);
  }
  if (res.status === 404) throw new Error(LOCAL_ONLY);
  if (!res.ok) return fail(res);
  return res.json();
}
