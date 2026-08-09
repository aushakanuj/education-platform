import { apiRequest, clearTokens, setTokens } from "./client";
import type {
  LoginRequest,
  MeResponse,
  ProvisionStudentRequest,
  TokenResponse,
} from "./types";

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const tokens = await apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    body: payload,
    auth: false,
  });
  setTokens(tokens);
  return tokens;
}

export async function provisionStudent(
  payload: ProvisionStudentRequest,
): Promise<MeResponse> {
  return apiRequest<MeResponse>("/auth/provision-student", {
    method: "POST",
    body: payload,
    auth: false,
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return apiRequest<MeResponse>("/auth/me");
}

export async function logout(): Promise<void> {
  const refresh = localStorage.getItem("ep_refresh_token");
  try {
    if (refresh) {
      await apiRequest<void>("/auth/logout", {
        method: "POST",
        body: { refresh_token: refresh },
        auth: false,
        skipRefresh: true,
      });
    }
  } finally {
    clearTokens();
  }
}
