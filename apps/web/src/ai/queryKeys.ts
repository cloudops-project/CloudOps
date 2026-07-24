import type { AITaskType } from "../types";

export interface AIHistoryFilters {
  sourceType?: "finding" | "risk_assessment" | "compliance_assessment";
  sourceId?: string;
  taskType?: AITaskType;
  page?: number;
  pageSize?: number;
}

function normalizedFilters(filters: AIHistoryFilters = {}) {
  return {
    sourceType: filters.sourceType ?? null,
    sourceId: filters.sourceId ?? null,
    taskType: filters.taskType ?? null,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 25,
  };
}

export const aiQueryKeys = {
  all: ["ai"] as const,
  organization: (organizationId: string) =>
    [...aiQueryKeys.all, "organization", organizationId] as const,
  history: (organizationId: string, filters: AIHistoryFilters = {}) =>
    [
      ...aiQueryKeys.organization(organizationId),
      "requests",
      normalizedFilters(filters),
    ] as const,
  request: (organizationId: string, requestId: string) =>
    [
      ...aiQueryKeys.organization(organizationId),
      "request",
      requestId,
    ] as const,
};
