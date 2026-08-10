import { withSupabase } from "npm:@supabase/server@1.4.1";
import {
  runReminderEmailWorker,
  type WorkerClient,
  type WorkerConfig,
} from "./worker.ts";

function requiredEnvironment(
  name: "RESEND_API_KEY" | "REMINDER_EMAIL_FROM",
): string {
  const value = Deno.env.get(name)?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export default {
  fetch: withSupabase(
    { auth: "secret:reminder_worker" },
    async (_request, context) => {
      let config: WorkerConfig;
      try {
        config = {
          resendApiKey: requiredEnvironment("RESEND_API_KEY"),
          from: requiredEnvironment("REMINDER_EMAIL_FROM"),
        };
      } catch (error) {
        const message = error instanceof Error
          ? error.message
          : "Worker configuration is unavailable";
        console.error(
          JSON.stringify({
            event: "reminder_email_worker_configuration_error",
            message,
          }),
        );
        return Response.json(
          { ok: false, error: "worker_configuration_error" },
          {
            status: 500,
          },
        );
      }

      try {
        return Response.json(
          await runReminderEmailWorker(
            context.supabaseAdmin as unknown as WorkerClient,
            config,
          ),
        );
      } catch {
        console.error(
          JSON.stringify({ event: "reminder_email_worker_claim_error" }),
        );
        return Response.json({ ok: false, error: "worker_unavailable" }, {
          status: 503,
        });
      }
    },
  ),
};
