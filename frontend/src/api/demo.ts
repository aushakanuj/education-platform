import type { DemoBootstrapResponse } from "./types";
import { apiRequest } from "./client";

export async function bootstrapDemoProgress(): Promise<DemoBootstrapResponse> {
  return apiRequest<DemoBootstrapResponse>("/me/demo/bootstrap", { method: "POST" });
}

export async function resetDemoProgress(): Promise<{ status: string; message: string }> {
  return apiRequest<{ status: string; message: string }>("/me/demo/reset", { method: "POST" });
}
