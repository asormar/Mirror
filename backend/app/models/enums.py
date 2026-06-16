import enum


class EntityType(enum.StrEnum):
    HEDGE_FUND = "HEDGE_FUND"
    MUTUAL_FUND = "MUTUAL_FUND"
    PENSION_FUND = "PENSION_FUND"
    INSIDER = "INSIDER"
    POLITICIAN_US_HOUSE = "POLITICIAN_US_HOUSE"
    POLITICIAN_US_SENATE = "POLITICIAN_US_SENATE"


class SourceType(enum.StrEnum):
    FORM_13F_HR = "FORM_13F_HR"
    FORM_13F_HR_A = "FORM_13F_HR_A"
    FORM_13G = "FORM_13G"
    FORM_13D = "FORM_13D"
    FORM_4 = "FORM_4"
    HOUSE_PTR = "HOUSE_PTR"
    SENATE_PTR = "SENATE_PTR"


class ParsingStatus(enum.StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class TradeAction(enum.StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class HoldingAction(enum.StrEnum):
    NEW = "NEW"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    UNCHANGED = "UNCHANGED"
    EXIT = "EXIT"


class LedgerEntryType(enum.StrEnum):
    INITIAL_DEPOSIT = "INITIAL_DEPOSIT"
    TRADE_BUY = "TRADE_BUY"
    TRADE_SELL = "TRADE_SELL"
    FEE = "FEE"
    ADJUSTMENT = "ADJUSTMENT"
