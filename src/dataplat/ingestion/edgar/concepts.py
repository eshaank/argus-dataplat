"""GAAP concept extraction with fallback mapping.

Companies use different XBRL concept names for the same line item.
This module maps our normalized field names to ordered lists of
GAAP concept alternatives, and extracts values from companyfacts JSON.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps our normalized column name → list of GAAP concept names to try (in order).
# First match wins.
CONCEPT_MAP: dict[str, list[str]] = {
    # ── Income Statement ──
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "cost_of_revenue": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": [
        "OperatingExpenses",
        "CostsAndExpenses",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "basic_eps": ["EarningsPerShareBasic"],
    "diluted_eps": ["EarningsPerShareDiluted"],
    "research_and_dev": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "sga_expenses": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ],
    "income_tax": [
        "IncomeTaxExpenseBenefit",
        "IncomeTaxesPaidNet",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
    ],
    "ebitda": [
        # Rarely filed directly — we compute it in the SDK if missing
    ],
    # ── Balance Sheet ──
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "noncurrent_assets": ["AssetsNoncurrent"],
    "total_liabilities": ["Liabilities"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "noncurrent_liabilities": ["LiabilitiesNoncurrent"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "long_term_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "short_term_debt": [
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "inventory": ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"],
    "accounts_receivable": [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
    ],
    "accounts_payable": [
        "AccountsPayableCurrent",
        "AccountsPayable",
    ],
    "goodwill": ["Goodwill"],
    # ── Cash Flow ──
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "investing_cash_flow": [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ],
    "financing_cash_flow": [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpenditureDiscontinuedOperations",
    ],
    "dividends_paid": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "Dividends",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    # ── Dilution & Share Activity ──
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
    "shares_issued": ["CommonStockSharesIssued"],
    "weighted_avg_shares_basic": [
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    "weighted_avg_shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    "stock_based_compensation": [
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
    ],
    "buyback_shares": [
        "StockRepurchasedAndRetiredDuringPeriodShares",
        "StockRepurchasedDuringPeriodShares",
        "TreasuryStockSharesAcquired",
    ],
    "buyback_value": [
        "PaymentsForRepurchaseOfCommonStock",
        "StockRepurchasedAndRetiredDuringPeriodValue",
        "TreasuryStockValueAcquiredCostMethod",
    ],
    "shares_issued_options": ["StockIssuedDuringPeriodSharesStockOptionsExercised"],
    "shares_issued_rsu_vested": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsVestedInPeriod",
    ],
    "unvested_rsu_shares": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber",
    ],
    "antidilutive_shares": [
        "AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount",
    ],
    "dividends_per_share": [
        "CommonStockDividendsPerShareDeclared",
        "CommonStockDividendsPerShareCashPaid",
    ],
    "issuance_proceeds": [
        "ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromStockOptionsExercised",
    ],
    # ── Authorized Headroom ──
    "shares_authorized": ["CommonStockSharesAuthorized"],
    "preferred_shares_authorized": ["PreferredStockSharesAuthorized"],
    "stock_plan_shares_authorized": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardNumberOfSharesAuthorized",
    ],
    "buyback_program_authorized": ["StockRepurchaseProgramAuthorizedAmount1"],
    # ── Warrants ──
    "warrants_outstanding": ["ClassOfWarrantOrRightOutstanding"],
    "warrant_exercise_price": ["ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1"],
    "warrant_shares_callable": ["ClassOfWarrantOrRightNumberOfSecuritiesCalledByWarrantsOrRights"],
    "warrants_fair_value": ["WarrantsAndRightsOutstanding"],
    "warrant_proceeds": ["ProceedsFromWarrantExercises"],
    # ── Convertible Debt ──
    "convertible_debt": [
        "ConvertibleDebt",
        "ConvertibleNotesPayable",
        "ConvertibleLongTermNotesPayable",
    ],
    "convertible_debt_current": [
        "ConvertibleDebtCurrent",
        "ConvertibleNotesPayableCurrent",
    ],
    "convertible_conversion_price": ["DebtInstrumentConvertibleConversionPrice1"],
    "convertible_conversion_ratio": ["DebtInstrumentConvertibleConversionRatio1"],
    "convertible_debt_proceeds": ["ProceedsFromConvertibleDebt"],
    "convertible_debt_repayments": ["RepaymentsOfConvertibleDebt"],
    "shares_from_conversion": ["StockIssuedDuringPeriodSharesConversionOfConvertibleSecurities"],
    # ── Options Pool ──
    "options_outstanding": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber",
    ],
    "options_exercisable": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsExercisableNumber",
    ],
    "options_weighted_avg_price": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice",
    ],
    "options_intrinsic_value": [
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingIntrinsicValue",
    ],
    # FUTURE: S-3 shelf capacity, ATM remaining — requires filing text parsing
}

# Valid form types for annual and quarterly filings
ANNUAL_FORMS = {"10-K", "20-F", "10-K/A", "20-F/A"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
ALL_FORMS = ANNUAL_FORMS | QUARTERLY_FORMS

# Fiscal period mapping
ANNUAL_FP = {"FY"}
QUARTERLY_FP = {"Q1", "Q2", "Q3"}


def _extract_concept_values(
    gaap: dict[str, Any],
    concept_names: list[str],
) -> list[dict]:
    """Try each concept name in order; return fact entries from the first match."""
    for name in concept_names:
        if name in gaap:
            concept_data = gaap[name]
            # Collect entries from all unit types (USD, shares, USD/shares, pure)
            entries = []
            for unit_entries in concept_data.get("units", {}).values():
                entries.extend(unit_entries)
            if entries:
                return entries
    return []


def extract_financials(companyfacts: dict) -> list[dict]:
    """Extract structured financial periods from a companyfacts JSON response.

    Returns a list of dicts, one per (period_end, fiscal_period) combination,
    with all normalized line items as keys.
    """
    facts = companyfacts.get("facts", {})
    gaap = facts.get("us-gaap", {})
    if not gaap:
        # Try IFRS for foreign filers
        gaap = facts.get("ifrs-full", {})
    if not gaap:
        return []

    # Build: {(end_date, fp, form): {field: value}}
    periods: dict[tuple[str, str, str], dict[str, Any]] = {}

    for field_name, concept_names in CONCEPT_MAP.items():
        if not concept_names:
            continue

        entries = _extract_concept_values(gaap, concept_names)

        for entry in entries:
            form = entry.get("form", "")
            fp = entry.get("fp", "")
            end = entry.get("end")
            if not end or not form or not fp:
                continue

            # Filter to actual financial filings
            if form not in ALL_FORMS:
                continue
            if fp not in (ANNUAL_FP | QUARTERLY_FP):
                continue

            key = (end, fp, form)
            if key not in periods:
                periods[key] = {
                    "period_end": end,
                    "period_start": entry.get("start"),
                    "fiscal_period": fp,
                    "form_type": form,
                    "filed_date": entry.get("filed"),
                    "accession_number": entry.get("accn"),
                }
            periods[key][field_name] = entry.get("val")

    # Deduplicate: prefer non-amendment forms, then latest filing date
    deduped: dict[tuple[str, str], dict] = {}
    for (end, fp, form), data in sorted(periods.items(), key=lambda x: (x[0][0], x[0][1], "A" not in x[0][2], x[1].get("filed_date", ""))):
        dedup_key = (end, fp)
        # Later entries (sorted) overwrite earlier ones — amendments win
        deduped[dedup_key] = data

    return list(deduped.values())
