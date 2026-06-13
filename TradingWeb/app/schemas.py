"""Pydantic request/response models for the TradingWeb API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str


class CreateRunRequest(BaseModel):
    ticker: str
    analysis_date: str
    analysts: List[str]
    research_depth: int
    llm_provider: str
    backend_url: Optional[str] = None
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None


class CreateRunResponse(BaseModel):
    id: int


class RunSummary(BaseModel):
    id: int
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    decision: Optional[str] = None
    llm_provider: Optional[str] = None
    deep_think_llm: Optional[str] = None
    quick_think_llm: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


class RunListResponse(BaseModel):
    runs: List[RunSummary]
    total: int


class RunDetailResponse(BaseModel):
    id: int
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    decision: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    selections: Dict[str, Any] = Field(default_factory=dict)
    agent_statuses: Dict[str, str] = Field(default_factory=dict)
    reports: Dict[str, str] = Field(default_factory=dict)


class StepItem(BaseModel):
    id: int
    ts: str
    kind: str
    agent: Optional[str] = None
    content: Optional[str] = None


class StepsResponse(BaseModel):
    steps: List[StepItem]
    status: str
    decision: Optional[str] = None
    agent_statuses: Dict[str, str] = Field(default_factory=dict)
    reports: Dict[str, str] = Field(default_factory=dict)
