"use client";

import { API_BASE_URL } from "@/lib/api";

export interface SignupInput {
  owner_name: string;
  email: string;
  password: string;
  phone?: string;
  establishment_name: string;
  segment: string;
  terms_accepted: boolean;
  consents: Record<string, boolean>;
}

export interface SignupAccepted {
  accepted: boolean;
  signup_id: string;
  message: string;
}

export class SignupApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "SignupApiError";
  }
}

export async function createSignup(input: SignupInput): Promise<SignupAccepted> {
  const response = await fetch(`${API_BASE_URL}/v1/public/signup`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new SignupApiError("signup_request_failed", response.status);
  }
  return (await response.json()) as SignupAccepted;
}


export interface SignupVerificationResult {
  signup_id: string;
  status: string;
  ready: boolean;
}

export async function verifySignupEmail(
  signupId: string,
  token: string,
): Promise<SignupVerificationResult> {
  const normalizedSignupId = signupId.trim();
  const normalizedToken = token.trim();
  if (!normalizedSignupId || !normalizedToken) {
    throw new SignupApiError("signup_verification_invalid", 400);
  }
  const response = await fetch(
    `${API_BASE_URL}/v1/public/signup/${encodeURIComponent(normalizedSignupId)}/verify-email`,
    {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token: normalizedToken }),
    },
  );
  if (!response.ok) {
    throw new SignupApiError("signup_verification_failed", response.status);
  }
  return (await response.json()) as SignupVerificationResult;
}
