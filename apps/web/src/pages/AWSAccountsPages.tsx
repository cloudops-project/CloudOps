import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Cloud, Play, PlugZap, Unplug } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { z } from "zod";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import {
  AccountCard,
  ConnectionStatusBadge,
  IAMSetupInstructions,
  PolicyViewer,
  ValidationResult,
} from "../components/AWSAccountComponents";
import { Field } from "../components/AuthCard";
import type {
  AWSAccount,
  AWSAccountDetail,
  AWSAccountOnboarding,
} from "../types";

const createSchema = z.object({
  name: z.string().trim().min(2, "Enter an account name."),
  account_id: z
    .string()
    .regex(/^\d{12}$/, "AWS Account ID must contain exactly 12 digits."),
});
const roleSchema = z.object({
  role_arn: z
    .string()
    .regex(
      /^arn:(aws|aws-us-gov|aws-cn):iam::\d{12}:role\/[A-Za-z0-9+=,.@_/-]+$/,
      "Enter a valid IAM role ARN.",
    ),
});
type CreateValues = z.infer<typeof createSchema>;
type RoleValues = z.infer<typeof roleSchema>;

function useOrganization() {
  const { me } = useAuth();
  return me?.organizations[0];
}

function useAccountDetail() {
  const { accountId } = useParams();
  return useQuery({
    queryKey: ["aws-account", accountId],
    enabled: Boolean(accountId),
    queryFn: () => api<AWSAccountDetail>(`/api/v1/aws/accounts/${accountId}`),
  });
}

export function AWSAccountsPage() {
  const org = useOrganization();
  const canManage = org && ["owner", "admin"].includes(org.role);
  const query = useQuery({
    queryKey: ["aws-accounts", org?.id],
    enabled: Boolean(org),
    queryFn: () =>
      api<AWSAccount[]>(`/api/v1/aws/accounts?organization_id=${org!.id}`),
  });
  if (!org) return <p>No organization selected.</p>;
  return (
    <section>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">AWS accounts</h1>
          <p className="text-slate-400">
            Secure cross-account IAM connections for {org.name}
          </p>
        </div>
        {canManage && (
          <Link className="button" to="/aws/accounts/new">
            <Cloud size={18} />
            Add AWS account
          </Link>
        )}
      </div>
      {query.isLoading && <p aria-live="polite">Loading AWS accounts…</p>}
      {query.isError && (
        <p role="alert" className="text-red-400">
          Unable to load AWS accounts.
        </p>
      )}
      {query.data?.length === 0 && (
        <div className="card text-slate-300">
          No AWS accounts are connected yet.
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {query.data?.map((account) => (
          <AccountCard key={account.id} account={account} />
        ))}
      </div>
    </section>
  );
}

export function AddAWSAccountPage() {
  const org = useOrganization();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateValues>({ resolver: zodResolver(createSchema) });
  if (!org || !["owner", "admin"].includes(org.role))
    return <Navigate to="/unauthorized" replace />;
  return (
    <section className="card max-w-2xl">
      <h1 className="text-3xl font-bold">Add AWS account</h1>
      <p className="mt-2 text-slate-400">
        CloudOps generates a unique external ID. No access keys are requested or
        stored.
      </p>
      <form
        className="mt-6 grid gap-4"
        onSubmit={handleSubmit(async (values) => {
          try {
            const result = await api<AWSAccountDetail>("/api/v1/aws/accounts", {
              method: "POST",
              body: JSON.stringify({ ...values, organization_id: org.id }),
            });
            navigate(`/aws/accounts/${result.account.id}`);
          } catch (reason) {
            setError(
              reason instanceof Error
                ? reason.message
                : "Unable to create account.",
            );
          }
        })}
      >
        <Field label="Account name" {...register("name")} />
        {errors.name && (
          <p role="alert" className="text-red-400">
            {errors.name.message}
          </p>
        )}
        <Field
          label="AWS Account ID"
          inputMode="numeric"
          {...register("account_id")}
        />
        {errors.account_id && (
          <p role="alert" className="text-red-400">
            {errors.account_id.message}
          </p>
        )}
        {error && (
          <p role="alert" className="text-red-400">
            {error}
          </p>
        )}
        <button className="button" disabled={isSubmitting}>
          Generate onboarding setup
        </button>
      </form>
    </section>
  );
}

export function AWSAccountDetailsPage() {
  const org = useOrganization();
  const query = useAccountDetail();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [onboarding, setOnboarding] = useState<AWSAccountOnboarding | null>(
    null,
  );
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RoleValues>({
    resolver: zodResolver(roleSchema),
    values: { role_arn: query.data?.account.role_arn ?? "" },
  });
  const update = useMutation({
    mutationFn: (values: RoleValues) =>
      api<AWSAccountDetail>(`/api/v1/aws/accounts/${query.data!.account.id}`, {
        method: "PATCH",
        body: JSON.stringify(values),
      }),
    onSuccess: (data) =>
      queryClient.setQueryData(["aws-account", data.account.id], data),
    onError: (reason) =>
      setError(reason instanceof Error ? reason.message : "Update failed."),
  });
  if (query.isLoading) return <p aria-live="polite">Loading AWS account…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-red-400">
        Unable to load AWS account.
      </p>
    );
  const { account } = query.data;
  const canManage = org && ["owner", "admin"].includes(org.role);
  const canDiscover =
    org &&
    ["owner", "admin", "security_analyst", "cloud_engineer"].includes(org.role);
  return (
    <section className="grid gap-5">
      <Link
        className="inline-flex items-center gap-2 text-blue-300"
        to="/aws/accounts"
      >
        <ArrowLeft size={18} />
        AWS accounts
      </Link>
      <div className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold">{account.name}</h1>
            <p className="font-mono text-slate-400">{account.account_id}</p>
          </div>
          <ConnectionStatusBadge status={account.connection_status} />
        </div>
      </div>
      {canManage ? (
        <div className="card">
          <p className="text-slate-300">
            External ID and trust-policy material are restricted onboarding
            data.
          </p>
          <button
            className="button mt-4"
            onClick={async () => {
              try {
                setOnboarding(
                  await api<AWSAccountOnboarding>(
                    `/api/v1/aws/accounts/${account.id}/onboarding`,
                  ),
                );
              } catch (reason) {
                setError(
                  reason instanceof Error
                    ? reason.message
                    : "Unable to load onboarding material.",
                );
              }
            }}
          >
            Load onboarding material
          </button>
        </div>
      ) : (
        <div className="card text-slate-400">
          Onboarding trust material is available only to organization owners and
          administrators.
        </div>
      )}
      {onboarding && (
        <>
          <div className="card">
            <p className="text-sm text-slate-400">External ID</p>
            <code className="break-all text-blue-300">
              {onboarding.external_id}
            </code>
          </div>
          <IAMSetupInstructions steps={onboarding.onboarding_instructions} />
          <div className="grid gap-5 xl:grid-cols-2">
            <PolicyViewer
              title="Trust policy"
              value={onboarding.trust_policy}
            />
            <PolicyViewer
              title="Permission policy"
              value={onboarding.permission_policy}
            />
          </div>
        </>
      )}
      {canManage && (
        <form
          className="card grid gap-3"
          onSubmit={handleSubmit((values) => update.mutate(values))}
        >
          <h2 className="text-xl font-bold">Role ARN</h2>
          <Field label="AWS IAM Role ARN" {...register("role_arn")} />
          {errors.role_arn && (
            <p role="alert" className="text-red-400">
              {errors.role_arn.message}
            </p>
          )}
          {error && (
            <p role="alert" className="text-red-400">
              {error}
            </p>
          )}
          <button className="button" disabled={update.isPending}>
            Save role ARN
          </button>
        </form>
      )}
      <div className="flex flex-wrap gap-3">
        {canManage && (
          <Link className="button" to={`/aws/accounts/${account.id}/validate`}>
            <PlugZap size={18} />
            Validate connection
          </Link>
        )}
        {canDiscover && account.connection_status === "connected" && (
          <Link className="button" to="/discovery/jobs">
            <Play size={18} />
            Run discovery
          </Link>
        )}
        {canManage && (
          <Link
            className="button-secondary"
            to={`/aws/accounts/${account.id}/disconnect`}
          >
            <Unplug size={18} />
            Disconnect
          </Link>
        )}
      </div>
    </section>
  );
}

export function ConnectionValidationPage() {
  const { accountId } = useParams();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () =>
      api<AWSAccountDetail>(`/api/v1/aws/accounts/${accountId}/validate`, {
        method: "POST",
      }),
  });
  return (
    <section className="card max-w-2xl">
      <h1 className="text-3xl font-bold">Validate AWS connection</h1>
      <p className="mt-2 text-slate-400">
        CloudOps will assume the configured role and immediately call STS
        GetCallerIdentity.
      </p>
      {mutation.data && (
        <div className="mt-5">
          <ValidationResult
            ok={mutation.data.account.connection_status === "connected"}
          >
            {mutation.data.account.connection_status === "connected"
              ? "AWS account connection verified."
              : `Validation failed: ${mutation.data.account.failure_reason ?? "unknown error"}`}
          </ValidationResult>
        </div>
      )}
      {mutation.isError && (
        <p role="alert" className="mt-5 text-red-400">
          Validation request failed.
        </p>
      )}
      <div className="mt-6 flex gap-3">
        <button
          className="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          Validate now
        </button>
        <button
          className="button-secondary"
          onClick={() => navigate(`/aws/accounts/${accountId}`)}
        >
          Back
        </button>
      </div>
    </section>
  );
}

export function ConnectionFailurePage() {
  const query = useAccountDetail();
  return (
    <section className="max-w-2xl">
      <ValidationResult ok={false}>
        <h1 className="text-xl font-bold">Connection validation failed</h1>
        <p>
          {query.data?.account.failure_reason ??
            "Review the trust policy, external ID, and role ARN, then retry."}
        </p>
      </ValidationResult>
    </section>
  );
}

export function DisconnectConfirmationPage() {
  const { accountId } = useParams();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () =>
      api<AWSAccountDetail>(`/api/v1/aws/accounts/${accountId}/disconnect`, {
        method: "POST",
      }),
    onSuccess: () => navigate(`/aws/accounts/${accountId}`),
  });
  return (
    <section className="card max-w-xl">
      <h1 className="text-3xl font-bold">Disconnect AWS account?</h1>
      <p className="mt-3 text-slate-300">
        CloudOps will retain the onboarding record but mark the connection
        disconnected.
      </p>
      {mutation.isError && (
        <p role="alert" className="mt-4 text-red-400">
          Unable to disconnect the account.
        </p>
      )}
      <div className="mt-6 flex gap-3">
        <button
          className="button bg-critical hover:bg-red-700"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          Confirm disconnect
        </button>
        <button className="button-secondary" onClick={() => navigate(-1)}>
          Cancel
        </button>
      </div>
    </section>
  );
}
