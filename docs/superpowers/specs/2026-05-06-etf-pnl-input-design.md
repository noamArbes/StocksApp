# ETF Form: P&L % Input Instead of Cost Basis

## Problem

When adding an ETF holding, users often don't know the original purchase price (cost basis). They do know the current value (fetched live) and total P&L since purchase as a percentage.

## Goal

Replace the "Total cost basis" field with a "Total gain/loss %" field for ETF holdings only. The app derives cost basis from the live price and stores it as usual — no data model changes.

## Scope

ETF category only (`category == "etf"`). Stocks and MMFs keep the existing cost basis field.

---

## Form Change

**Before (ETF form):**
- Shares owned
- Total cost basis (what you paid in total)
- Currency

**After (ETF form):**
- Shares owned
- Total gain/loss % (e.g. `15` for +15%, `-8` for -8%)
- Currency (still relevant for TASE ETFs in ILS vs US ETFs in USD)

Stocks and MMFs: unchanged.

---

## Derivation Logic

In `_holding_from_form()`, when `category == "etf"`:

1. Read `pl_pct` from the form (the gain/loss %)
2. Fetch current price using `checker.get_price_with_change(ticker)` (yfinance) or `tase.get_price(tase_id, tase_type)` (TASE)
3. Compute: `cost_basis = (current_price × shares) / (1 + pl_pct / 100)`
4. Store `cost_basis` in the holding dict as normal

No changes to the savings view, P&L display, or data model.

---

## Validation & Error Handling

| Condition | Behaviour |
|---|---|
| `pl_pct` missing or non-numeric | Form error: "Total gain/loss % is required and must be a number" |
| `pl_pct == -100` | Form error: "Gain/loss % cannot be -100%" (division by zero) |
| Price fetch fails at submission | Form error: "Could not fetch current price — please try again" |
| All other categories | `cost_basis` field required as before |

---

## Files Changed

| File | Change |
|---|---|
| `templates/savings_form.html` | Show P&L % field instead of cost basis for ETFs; show cost basis for stocks/MMFs |
| `app.py` (`_holding_from_form`) | For ETFs: read `pl_pct`, fetch price, derive cost basis |
| `tests/test_app.py` | New tests for ETF P&L % derivation, validation errors, price fetch failure |
