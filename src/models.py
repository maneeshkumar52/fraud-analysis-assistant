from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FlaggedTransaction(BaseModel):
    transaction_id: str
    customer_id: str
    amount: float
    currency: str = "GBP"
    merchant_name: str
    merchant_category: str
    location_country: str
    location_city: str
    timestamp: str
    flag_reason: str
    flag_score: float = Field(..., ge=0.0, le=1.0)


class CustomerRiskProfile(BaseModel):
    customer_id: str
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    risk_factors: List[str]
    typical_transaction_range_min: float
    typical_transaction_range_max: float
    usual_merchants: List[str]
    usual_locations: List[str]
    account_age_days: int
    previous_fraud_flags: int
    last_updated: str


class FraudPattern(BaseModel):
    pattern_id: str
    pattern_name: str
    description: str
    similarity_score: float
    historical_cases: int


class AnalysisRequest(BaseModel):
    transaction: FlaggedTransaction
    stream: bool = True


class SimulateRequest(BaseModel):
    scenario: str = "high_risk"  # "high_risk", "low_risk", "velocity"
