import { apiClient } from "./client";

export type AssistantRequest = {
  prompt: string;
};

export type AssistantResponse = {
  answer: string;
  chartConfig?: Record<string, unknown>;
};

export const askAssistant = async (payload: AssistantRequest): Promise<AssistantResponse> =>
  apiClient.request<AssistantResponse, AssistantRequest>({
    method: "POST",
    path: "/assistant/query",
    body: payload,
  });
