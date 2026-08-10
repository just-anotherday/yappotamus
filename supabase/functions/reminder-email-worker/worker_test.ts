import {
  assertEquals,
  assertStringIncludes,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  type ClaimedDelivery,
  classifyProviderFailure,
  DELIVERY_CONCURRENCY,
  idempotencyKey,
  runReminderEmailWorker,
  type WorkerClient,
} from "./worker.ts";

const delivery: ClaimedDelivery = {
  delivery_id: "7ec00000-0000-4000-8000-000000000001",
  reminder_id: "8ec00000-0000-4000-8000-000000000001",
  user_id: "9ec00000-0000-4000-8000-000000000001",
  lock_token: "aec00000-0000-4000-8000-000000000001",
  attempt_count: 1,
  subject: "Durable subject",
  text_body: "Durable plain text body",
};
const config = {
  resendApiKey: "test-key",
  from: "YapVibes <test@example.com>",
};

function clientFor(
  options: {
    user?: { email?: string | null } | null;
    authError?: boolean;
    completion?: boolean;
    deliveries?: ClaimedDelivery[];
  } = {},
) {
  const calls: Array<{ name: string; args: Record<string, unknown> }> = [];
  const client: WorkerClient = {
    rpc: <T>(name: string, args: Record<string, unknown>) => {
      calls.push({ name, args });
      if (name === "claim_reminder_email_deliveries") {
        return Promise.resolve({
          data: (options.deliveries ?? [delivery]) as T,
          error: null,
        });
      }
      if (name === "complete_reminder_email_delivery") {
        return Promise.resolve({
          data: (options.completion ?? true) as T,
          error: null,
        });
      }
      return Promise.resolve({ data: true as T, error: null });
    },
    auth: {
      admin: {
        getUserById: () =>
          Promise.resolve({
            data: {
              user: options.user === undefined
                ? { email: "person@example.com" }
                : options.user,
            },
            error: options.authError ? { message: "unavailable" } : null,
          }),
      },
    },
  };
  return { client, calls };
}

function responseFetch(
  status = 200,
  payload: unknown = { id: "provider-message-id" },
) {
  return (_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(
      new Response(JSON.stringify(payload), {
        status,
        headers: { "content-type": "application/json" },
      }),
    );
}

Deno.test("idempotency key is deterministic and delivery scoped", () => {
  assertEquals(
    idempotencyKey(delivery.delivery_id),
    "reminder-email/7ec00000-0000-4000-8000-000000000001",
  );
  assertEquals(
    idempotencyKey(delivery.delivery_id),
    idempotencyKey(delivery.delivery_id),
  );
});

Deno.test("sends durable plain-text content and completes with the claim token", async () => {
  const { client, calls } = clientFor();
  let request: Request | undefined;
  const fetcher = (input: RequestInfo | URL, init?: RequestInit) => {
    request = new Request(input, init);
    return Promise.resolve(
      new Response(JSON.stringify({ id: "provider-message-id" }), {
        status: 200,
      }),
    );
  };
  const summary = await runReminderEmailWorker(
    client,
    config,
    fetcher as typeof fetch,
  );
  assertEquals(summary.sent, 1);
  assertEquals(await request!.json(), {
    from: config.from,
    to: ["person@example.com"],
    subject: delivery.subject,
    text: delivery.text_body,
  });
  assertEquals(
    request!.headers.get("Idempotency-Key"),
    idempotencyKey(delivery.delivery_id),
  );
  assertEquals(
    calls.find((call) => call.name === "complete_reminder_email_delivery")
      ?.args,
    {
      p_delivery_id: delivery.delivery_id,
      p_lock_token: delivery.lock_token,
      p_provider_message_id: "provider-message-id",
    },
  );
});

Deno.test(
  "missing Auth user or email is recorded as a permanent failure without sending",
  async () => {
    for (const user of [null, {}]) {
      const { client, calls } = clientFor({ user });
      const summary = await runReminderEmailWorker(
        client,
        config,
        responseFetch() as typeof fetch,
      );
      assertEquals(summary.permanent_failures, 1);
      assertEquals(
        calls.find((call) =>
          call.name === "record_reminder_email_delivery_failure"
        )?.args
          .p_retryable,
        false,
      );
    }
  },
);

Deno.test("network, 5xx, and rate-limit failures are retryable", async () => {
  const network = () => Promise.reject(new Error("network unavailable"));
  for (
    const fetcher of [
      network,
      responseFetch(503, { type: "internal_server_error" }),
      responseFetch(429, { type: "rate_limit_exceeded" }),
    ]
  ) {
    const { client, calls } = clientFor();
    const summary = await runReminderEmailWorker(
      client,
      config,
      fetcher as typeof fetch,
    );
    assertEquals(summary.retryable_failures, 1);
    assertEquals(
      calls.find((call) =>
        call.name === "record_reminder_email_delivery_failure"
      )?.args
        .p_retryable,
      true,
    );
  }
});

Deno.test("permanent provider failures and idempotency collisions are classified safely", () => {
  assertEquals(
    classifyProviderFailure(422, { type: "validation_error" }).retryable,
    false,
  );
  assertEquals(
    classifyProviderFailure(401, { type: "invalid_api_key" }).retryable,
    false,
  );
  assertEquals(
    classifyProviderFailure(409, { type: "concurrent_idempotent_requests" })
      .retryable,
    true,
  );
  assertEquals(
    classifyProviderFailure(409, { type: "invalid_idempotent_request" })
      .retryable,
    false,
  );
  assertEquals(
    classifyProviderFailure(429, { type: "daily_quota_exceeded" }).retryable,
    false,
  );
});

Deno.test(
  "completion failure does not issue another provider send and never exposes private fields",
  async () => {
    const { client } = clientFor({ completion: false });
    let sends = 0;
    const summary = await runReminderEmailWorker(
      client,
      config,
      (() => {
        sends++;
        return Promise.resolve(
          new Response(JSON.stringify({ id: "provider-message-id" }), {
            status: 200,
          }),
        );
      }) as typeof fetch,
    );
    assertEquals(sends, 1);
    assertEquals(summary.finalization_failures, 1);
    const json = JSON.stringify(summary);
    assertEquals(json.includes("person@example.com"), false);
    assertEquals(json.includes(delivery.text_body), false);
    assertEquals(json.includes(delivery.lock_token), false);
    assertEquals(json.includes(config.resendApiKey), false);
  },
);

Deno.test("no more than two provider operations run concurrently", async () => {
  const deliveries = Array.from({ length: 6 }, (_, index) => ({
    ...delivery,
    delivery_id: `7ec00000-0000-4000-8000-00000000000${index}`,
    lock_token: `aec00000-0000-4000-8000-00000000000${index}`,
  }));
  const { client } = clientFor({ deliveries });
  let inFlight = 0;
  let observed = 0;
  const fetcher = async () => {
    inFlight++;
    observed = Math.max(observed, inFlight);
    await new Promise((resolve) => setTimeout(resolve, 5));
    inFlight--;
    return new Response(JSON.stringify({ id: "provider-message-id" }), {
      status: 200,
    });
  };
  const summary = await runReminderEmailWorker(
    client,
    config,
    fetcher as typeof fetch,
  );
  assertEquals(summary.sent, 6);
  assertEquals(observed <= DELIVERY_CONCURRENCY, true);
});

Deno.test("safe provider classifier does not preserve untrusted provider messages", () => {
  const failure = classifyProviderFailure(422, {
    type: "validation_error",
    message: "person@example.com durable body test-key",
  });
  assertStringIncludes(failure.safeError, "resend_http_422");
  assertEquals(failure.safeError.includes("person@example.com"), false);
});
