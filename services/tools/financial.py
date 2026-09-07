from datetime import datetime, timezone, timedelta
from services.db import supabase

def _get_current_time_nepal():
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

async def log_expense(amount: float, category: str, description: str) -> str:
    """
    Logs an expense to the financial_ledger table.
    """
    if not supabase:
        return "Financial ledger is currently offline."

    try:
        data = {
            "amount": float(amount),
            "category": category.strip().lower(),
            "description": description.strip(),
            "logged_at": _get_current_time_nepal().isoformat()
        }
        supabase.table("financial_ledger").insert(data).execute()
        return f"Logged expense of {amount} for '{description}' under '{category}'."
    except Exception as e:
        print(f"Error logging expense: {e}")
        return f"Encountered an error while updating the ledger: {str(e)}"


async def get_expense_summary(days_back: int = 7) -> str:
    """
    Retrieves a summary of expenses for the given number of days.
    """
    if not supabase:
        return "Financial ledger is currently offline."

    try:
        threshold_date = (_get_current_time_nepal() - timedelta(days=days_back)).isoformat()
        response = (
            supabase.table("financial_ledger")
            .select("amount, category")
            .gte("logged_at", threshold_date)
            .execute()
        )

        records = response.data or []
        if not records:
            return f"No expenses recorded in the last {days_back} days."

        total_spent = sum(r["amount"] for r in records)
        category_totals: dict[str, float] = {}
        for r in records:
            cat = r["category"]
            category_totals[cat] = category_totals.get(cat, 0.0) + float(r["amount"])

        breakdown = ", ".join([f"{cat}: {amt:,.2f}" for cat, amt in category_totals.items()])
        return f"Total spent over the last {days_back} days: {total_spent:,.2f}. Breakdown: {breakdown}."
    except Exception as e:
        print(f"Error fetching expense summary: {e}")
        return f"Error reading financial ledger: {str(e)}"
