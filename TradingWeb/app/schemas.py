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
    provider_profile_id: Optional[int] = None
    llm_provider: str
    backend_url: Optional[str] = None
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    checkpoint_enabled: bool = False


class CreateRunResponse(BaseModel):
    id: int


class RunSummary(BaseModel):
    id: int
    username: Optional[str] = None
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    decision: Optional[str] = None
    provider_profile_id: Optional[int] = None
    provider_profile_name: Optional[str] = None
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
    username: Optional[str] = None
    ticker: str
    analysis_date: str
    asset_type: str
    status: str
    decision: Optional[str] = None
    error: Optional[str] = None
    provider_profile_id: Optional[int] = None
    provider_profile_name: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None
    selections: Dict[str, Any] = Field(default_factory=dict)
    agent_statuses: Dict[str, str] = Field(default_factory=dict)
    reports: Dict[str, str] = Field(default_factory=dict)
    checkpoint_enabled: bool = False
    memory_log_path: Optional[str] = None


class ProviderProfileBase(BaseModel):
    name: str
    provider_key: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    enabled: bool = True


class ProviderProfileCreate(ProviderProfileBase):
    pass


class ProviderProfileUpdate(BaseModel):
    name: Optional[str] = None
    provider_key: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    quick_think_llm: Optional[str] = None
    deep_think_llm: Optional[str] = None
    output_language: Optional[str] = None
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    enabled: Optional[bool] = None


class ProviderProfileResponse(ProviderProfileBase):
    id: int
    label: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


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


class BatchRunRequest(BaseModel):
    tickers: List[str]
    analysis_date: str
    analysts: List[str]
    research_depth: int
    provider_profile_id: Optional[int] = None
    llm_provider: str
    backend_url: Optional[str] = None
    quick_think_llm: str
    deep_think_llm: str
    output_language: str = "English"
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    checkpoint_enabled: bool = False


class BatchRunResponse(BaseModel):
    ids: List[int]
