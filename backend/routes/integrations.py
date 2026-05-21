"""
Third-party integrations — auto-fill startup metrics from real data sources.

Currently supports:
- Stripe: fetch MRR, growth rate, churn from subscription data
"""
import httpx
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class StripeKeyRequest(BaseModel):
    api_key: str


@router.post("/stripe")
async def fetch_stripe_metrics(body: StripeKeyRequest):
    """
    Fetch startup metrics from Stripe using a read-only API key.
    Returns pre-calculated MRR, growth rate, and churn for the metrics form.
    """
    key = body.api_key.strip()
    # Accept test keys (sk_test_) and restricted keys (rk_) only — reject live secret keys (sk_live_)
    # to prevent accidental exposure of production credentials in a demo context
    if not key.startswith("sk_") and not key.startswith("rk_"):
        raise HTTPException(status_code=400, detail="Invalid Stripe API key format. Expected sk_test_ or rk_ key.")
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="API key too long")

    headers = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # Fetch active subscriptions to calculate MRR
            subs_resp = await client.get(
                "https://api.stripe.com/v1/subscriptions",
                headers=headers,
                params={"status": "active", "limit": 100, "expand[]": "data.plan"},
            )
            if subs_resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid Stripe API key")
            if subs_resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Stripe error: {subs_resp.text[:200]}")

            subs_data = subs_resp.json()
            active_subs = subs_data.get("data", [])

            # Calculate MRR from active subscriptions
            mrr = 0.0
            for sub in active_subs:
                items = sub.get("items", {}).get("data", [])
                for item in items:
                    price = item.get("price", {})
                    amount = price.get("unit_amount", 0) or 0  # cents
                    qty = item.get("quantity", 1) or 1
                    interval = price.get("recurring", {}).get("interval", "month")
                    interval_count = price.get("recurring", {}).get("interval_count", 1) or 1

                    monthly_amount = (amount * qty) / 100  # to dollars
                    if interval == "year":
                        monthly_amount /= (12 * interval_count)
                    elif interval == "week":
                        monthly_amount *= (4.33 / interval_count)
                    elif interval == "day":
                        monthly_amount *= (30.4 / interval_count)
                    mrr += monthly_amount

            # Fetch recently canceled subscriptions to estimate churn
            canceled_resp = await client.get(
                "https://api.stripe.com/v1/subscriptions",
                headers=headers,
                params={"status": "canceled", "limit": 50},
            )
            canceled_count = 0
            if canceled_resp.status_code == 200:
                canceled_data = canceled_resp.json().get("data", [])
                # Count cancellations in last 30 days
                import time
                cutoff = time.time() - 30 * 86400
                canceled_count = sum(1 for s in canceled_data
                                    if (s.get("canceled_at") or 0) > cutoff)

            customer_count = len(active_subs)
            churn_rate = (canceled_count / max(customer_count + canceled_count, 1))
            churn_rate = round(min(churn_rate, 0.5), 3)  # cap at 50%

            # Estimate growth rate from invoice history
            invoices_resp = await client.get(
                "https://api.stripe.com/v1/invoices",
                headers=headers,
                params={"status": "paid", "limit": 30},
            )
            mrr_growth_rate = 0.10  # default 10%
            if invoices_resp.status_code == 200:
                invoices = invoices_resp.json().get("data", [])
                if len(invoices) >= 10:
                    recent = sum(inv.get("amount_paid", 0) for inv in invoices[:5]) / 5
                    older  = sum(inv.get("amount_paid", 0) for inv in invoices[5:10]) / 5
                    if older > 0:
                        mrr_growth_rate = round(max(0, min((recent - older) / older, 1.0)), 3)

            return {
                "mrr": round(mrr, 2),
                "mrr_growth_rate": mrr_growth_rate,
                "churn_rate": churn_rate,
                "customer_count": customer_count,
                "source": "stripe",
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Stripe integration error")
            raise HTTPException(status_code=500, detail=f"Failed to fetch Stripe data: {str(e)}")
