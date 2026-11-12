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
  old_pipe_pct: number;
  combined_sewer_pct: number;
  topic_rank: number | null;
  topic_value: string | null;
};

export type Excerpt = {
  source: string;
  page: number;
  ward_id: number | null;
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

export async function getWards(): Promise<Ward[]> {
  const res = await fetch("/api/wards");
  if (!res.ok) return fail(res);
  return res.json();
}

export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) return fail(res);
  return res.json();
}
