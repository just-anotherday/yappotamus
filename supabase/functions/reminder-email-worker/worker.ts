export const BATCH_SIZE = 10;
export const DELIVERY_CONCURRENCY = 2;
const MAX_SAFE_ERROR_LENGTH = 1000;

export type ClaimedDelivery = {
  delivery_id: string;
  reminder_id: string;
  user_id: string;
  lock_token: string;
  attempt_count: number;
  subject: string;
  text_body: string;
};

export type RpcResult<T> = {
  data: T | null;
  error: { message?: string } | null;
};

export interface WorkerClient {
  rpc<T>(name: string, args: Record<string, unknown>): Promise<RpcResult<T>>;
  auth: {
    admin: {
      getUserById(userId: string): Promise<{
        data: { user: { email?: string | null } | null };
        error: { message?: string } | null;
      }>;
    };
  };
}

export type WorkerConfig = { resendApiKey: string; from: string };
export type FetchLike = typeof fetch;

export type ProviderFailure = {
  retryable: boolean;
  safeError: string;
  category:
    | "network"
    | "provider_transient"
    | "provider_permanent"
    | "provider_quota"
    | "idempotency";
};

export type WorkerSummary = {
  ok: true;
  claimed: number;
  sent: number;
  failed: number;
  retryable_failures: number;
  permanent_failures: number;
  finalization_failures: number;
};

export function idempotencyKey(deliveryId: string): string {
  return `reminder-email/${deliveryId}`;
}

export function sanitizeError(value: string): string {
  return value.replace(/[\r\n]+/g, " ").slice(0, MAX_SAFE_ERROR_LENGTH);
}

function providerType(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const candidate = (payload as Record<string, unknown>).type;
  return typeof candidate === "string" && /^[a-z0-9_]+$/i.test(candidate)
    ? candidate
    : null;
}

export function classifyProviderFailure(
  status: number | null,
  payload: unknown,
): ProviderFailure {
  const type = providerType(payload);
  if (type === "concurrent_idempotent_requests") {
    return {
      retryable: true,
      safeError: "resend_concurrent_idempotent_requests",
      category: "idempotency",
    };
  }
  if (
    type === "invalid_idempotent_request" || type === "invalid_idempotency_key"
  ) {
    return {
      retryable: false,
      safeError: `resend_${type}`,
      category: "idempotency",
    };
  }
  if (type === "rate_limit_exceeded") {
    return {
      retryable: true,
      safeError: "resend_rate_limit_exceeded",
      category: "provider_transient",
    };
  }
  if (type === "daily_quota_exceeded" || type === "monthly_quota_exceeded") {
    return {
      retryable: false,
      safeError: `resend_${type}`,
      category: "provider_quota",
    };
  }
  if (status !== null && status >= 500) {
    return {
      retryable: true,
      safeError: `resend_http_${status}`,
      category: "provider_transient",
    };
  }
  return {
    retryable: false,
    safeError: `resend_http_${status ?? "network"}`,
    category: "provider_permanent",
  };
}

async function recordFailure(
  client: WorkerClient,
  delivery: ClaimedDelivery,
  retryable: boolean,
  safeError: string,
): Promise<void> {
  const { data, error } = await client.rpc<boolean>(
    "record_reminder_email_delivery_failure",
    {
      p_delivery_id: delivery.delivery_id,
      p_lock_token: delivery.lock_token,
      p_retryable: retryable,
      p_safe_error: sanitizeError(safeError),
    },
  );
  if (error || data !== true) {
    throw new Error("failure RPC did not confirm the claimed delivery");
  }
}

async function sendWithResend(
  fetcher: FetchLike,
  config: WorkerConfig,
  delivery: ClaimedDelivery,
  recipient: string,
): Promise<{ id: string } | ProviderFailure> {
  let response: Response;
  try {
    response = await fetcher("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.resendApiKey}`,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey(delivery.delivery_id),
        "User-Agent": "yapvibes-reminder-email-worker/1.0",
      },
      body: JSON.stringify({
        from: config.from,
        to: [recipient],
        subject: delivery.subject,
        text: delivery.text_body,
      }),
    });
  } catch {
    return {
      retryable: true,
      safeError: "resend_network_error",
      category: "network",
    };
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    /* a malformed provider response remains safely classified */
  }
  if (!response.ok) return classifyProviderFailure(response.status, payload);
  const id = payload && typeof payload === "object"
    ? (payload as Record<string, unknown>).id
    : null;
  if (typeof id !== "string" || id.length === 0 || id.length > 255) {
    return {
      retryable: true,
      safeError: "resend_success_response_missing_id",
      category: "provider_transient",
    };
  }
  return { id };
}

type DeliveryOutcome =
  | "sent"
  | "retryable_failure"
  | "permanent_failure"
  | "finalization_failure";

export async function processDelivery(
  client: WorkerClient,
  config: WorkerConfig,
  fetcher: FetchLike,
  delivery: ClaimedDelivery,
): Promise<DeliveryOutcome> {
  const userResult = await client.auth.admin.getUserById(delivery.user_id);
  if (userResult.error) {
    await recordFailure(client, delivery, true, "auth_user_lookup_failed");
    return "retryable_failure";
  }
  const email = userResult.data.user?.email?.trim();
  if (!email) {
    await recordFailure(
      client,
      delivery,
      false,
      userResult.data.user ? "auth_user_email_missing" : "auth_user_not_found",
    );
    return "permanent_failure";
  }

  const sendResult = await sendWithResend(fetcher, config, delivery, email);
  if ("retryable" in sendResult) {
    await recordFailure(
      client,
      delivery,
      sendResult.retryable,
      sendResult.safeError,
    );
    return sendResult.retryable ? "retryable_failure" : "permanent_failure";
  }

  const completion = await client.rpc<boolean>(
    "complete_reminder_email_delivery",
    {
      p_delivery_id: delivery.delivery_id,
      p_lock_token: delivery.lock_token,
      p_provider_message_id: sendResult.id,
    },
  );
  if (completion.error || completion.data !== true) {
    console.error(
      JSON.stringify({
        event: "reminder_email_completion_failed",
        delivery_id: delivery.delivery_id,
        provider_message_id: sendResult.id,
      }),
    );
    return "finalization_failure";
  }
  console.info(
    JSON.stringify({
      event: "reminder_email_sent",
      delivery_id: delivery.delivery_id,
      provider_message_id: sendResult.id,
      attempt_count: delivery.attempt_count,
    }),
  );
  return "sent";
}

export async function mapWithConcurrency<T, R>(
  values: T[],
  limit: number,
  operation: (value: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(values.length);
  let nextIndex = 0;
  const workers = Array.from(
    { length: Math.min(limit, values.length) },
    async () => {
      while (nextIndex < values.length) {
        const index = nextIndex++;
        results[index] = await operation(values[index]);
      }
    },
  );
  await Promise.all(workers);
  return results;
}

export async function runReminderEmailWorker(
  client: WorkerClient,
  config: WorkerConfig,
  fetcher: FetchLike = fetch,
): Promise<WorkerSummary> {
  const claim = await client.rpc<ClaimedDelivery[]>(
    "claim_reminder_email_deliveries",
    {
      p_limit: BATCH_SIZE,
    },
  );
  if (claim.error || !claim.data) {
    throw new Error("unable to claim reminder email deliveries");
  }
  const outcomes = await mapWithConcurrency(
    claim.data,
    DELIVERY_CONCURRENCY,
    async (delivery) => {
      try {
        return await processDelivery(client, config, fetcher, delivery);
      } catch {
        console.error(
          JSON.stringify({
            event: "reminder_email_failure_finalization_failed",
            delivery_id: delivery.delivery_id,
          }),
        );
        return "finalization_failure" as const;
      }
    },
  );
  return {
    ok: true,
    claimed: claim.data.length,
    sent: outcomes.filter((outcome) => outcome === "sent").length,
    failed: outcomes.filter((outcome) => outcome !== "sent").length,
    retryable_failures:
      outcomes.filter((outcome) => outcome === "retryable_failure").length,
    permanent_failures:
      outcomes.filter((outcome) => outcome === "permanent_failure").length,
    finalization_failures:
      outcomes.filter((outcome) => outcome === "finalization_failure").length,
  };
}
