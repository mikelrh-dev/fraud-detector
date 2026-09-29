import { http, HttpResponse } from "msw";
import type { ScoreResponse } from "../../api/transactions";

interface FixtureBase {
  transaction_id: string;
  threshold: number;
  created_at: string;
  friction_level: string;
  action: string | null;
}

const baseResponse: FixtureBase = {
  transaction_id: "test-uuid",
  threshold: 40,
  created_at: new Date().toISOString(),
  friction_level: "allow",
  action: null,
};

const fixtures: Record<string, ScoreResponse> = {
  legitimate: {
    ...baseResponse,
    rule_score: 10,
    ml_score: 12.3,
    ensemble_score: 11,
    classification: "legitimate",
    fired_rules: [],
  },
  review: {
    ...baseResponse,
    rule_score: 50,
    ml_score: 55,
    ensemble_score: 62,
    classification: "review",
    fired_rules: ["high_amount"],
    friction_level: "challenge",
    action: "request_3d_secure",
  },
  fraud: {
    ...baseResponse,
    rule_score: 90,
    ml_score: 88,
    ensemble_score: 91,
    classification: "fraud",
    fired_rules: ["high_amount", "high_velocity", "new_merchant"],
    friction_level: "block",
    action: "block_transaction",
  },
};

export const handlers = [
  http.post("*/api/v1/transactions", async ({ request }) => {
    const body = (await request.json()) as { amount?: number };
    const amount = body?.amount ?? 0;
    const key = amount > 5000 ? "fraud" : amount > 1000 ? "review" : "legitimate";
    return HttpResponse.json(fixtures[key]);
  }),

  http.get("*/api/v1/transactions", ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get("page") || 1);
    const items = Array.from({ length: 10 }, (_, i) => {
      const isReview = i % 3 === 0;
      return {
        id: `tx-${page}-${i}`,
        amount: 100 + i * 500,
        currency: "USD",
        merchant_name: `Merchant ${i}`,
        merchant_category: "retail",
        card_last4: "1234",
        status: isReview ? "flagged" : "approved",
        risk_score: isReview ? 62 : 15,
        classification: isReview ? "review" : "legitimate",
        scoring: null,
        user_id: "00000000-0000-0000-0000-000000000001",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    });
    return HttpResponse.json({ items, total: 50, page, page_size: 10 });
  }),

  http.get("*/api/v1/transactions/:id", ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      amount: 1500,
      currency: "USD",
      merchant_name: "Test Merchant",
      merchant_category: "retail",
      card_last4: "1234",
      status: "flagged",
      risk_score: 62.0,
      classification: "review",
      scoring: {
        rule_score: 50,
        ml_score: 55,
        ensemble_score: 62,
        threshold: 60,
        classification: "review",
        // FRD-SHP-002: deterministic top-5, ordered by |contribution| desc
        shap_contributions: [
          { feature: "amount", contribution: 35 },
          { feature: "tx_count_last_1h", contribution: 18 },
          { feature: "tx_count_last_5min", contribution: 12 },
          { feature: "merchant_risk_level", contribution: -5 },
          { feature: "amount_round_number", contribution: -2 },
        ],
      },
      user_id: "00000000-0000-0000-0000-000000000001",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }),

  http.get("*/api/v1/transactions/:id/report", () =>
    HttpResponse.json({ detail: "Report not found" }, { status: 404 }),
  ),

  http.get("*/api/v1/monitoring/dashboard", () => {
    return HttpResponse.json({
      total_transactions: 1234,
      fraud_percentage: 2.3,
      avg_score: 18.5,
      active_alerts: 5,
      model_status: "active",
    });
  }),

  http.get("*/api/v1/alerts", () => {
    const items = Array.from({ length: 5 }, (_, i) => ({
      id: `alert-${i}`,
      transaction_id: `tx-alert-${i}`,
      status: i % 3 === 0 ? "open" : i % 3 === 1 ? "reviewed" : "resolved",
      score: 45 + i * 15,
      threshold: 40,
      classification: i % 3 === 0 ? "fraud" : i % 3 === 1 ? "review" : "legitimate",
      reviewed_by: null,
      reviewed_at: null,
      created_at: new Date().toISOString(),
    }));
    return HttpResponse.json({ items, total: 5, page: 1, page_size: 20 });
  }),
];
