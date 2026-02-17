"""Pydantic models for Triqai API request and response structures.

Updated for API v1.1.0: entities array pattern with ConfidenceWithReasons.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    """Transaction direction type."""

    EXPENSE = "expense"
    INCOME = "income"


class TransactionChannel(str, Enum):
    """How the transaction was conducted."""

    IN_STORE = "in_store"
    ONLINE = "online"
    MOBILE_APP = "mobile_app"
    ATM = "atm"
    BANK_TRANSFER = "bank_transfer"
    UNKNOWN = "unknown"


class SubscriptionType(str, Enum):
    """Subscription category types."""

    STREAMING = "streaming"
    SOFTWARE = "software"
    NEWS = "news"
    FITNESS = "fitness"
    MOBILE = "mobile"
    GAMING = "gaming"
    UTILITIES = "utilities"
    OTHER = "other"


class EntityType(str, Enum):
    """Entity types in the entities array."""

    MERCHANT = "merchant"
    LOCATION = "location"
    INTERMEDIARY = "intermediary"
    PERSON = "person"


# Request Models


class Transaction(BaseModel):
    """Input transaction to enrich."""

    title: str = Field(..., min_length=1, max_length=256, description="Transaction title from bank statement")
    country: str = Field(..., pattern=r"^[A-Za-z]{2}$", description="ISO 3166-1 alpha-2 country code")
    type: TransactionType = Field(..., description="Transaction direction (expense/income)")
    comment: str | None = Field(None, description="Optional comment about the transaction")

    def to_api_request(self) -> dict[str, str]:
        """Convert to API request payload."""
        return {
            "title": self.title,
            "country": self.country.upper(),
            "type": self.type.value,
        }


# Response Models


class Coordinates(BaseModel):
    """Geographic coordinates."""

    latitude: float
    longitude: float


class CategoryCode(BaseModel):
    """Industry classification codes."""

    mcc: int | None = Field(None, description="Merchant Category Code")
    sic: int | None = Field(None, description="Standard Industrial Classification")
    naics: int | None = Field(None, description="NAICS code")


class Category(BaseModel):
    """Category information.

    Handles both nested format (code.mcc) and flat format (mcc directly on category).
    """

    name: str
    # Nested code object (from API responses)
    code: CategoryCode | None = None
    # Flat fields (from CategoryInfo format in /v1/categories)
    mcc: int | None = None
    sic: int | None = None
    naics: int | None = None
    # Additional fields from CategoryInfo
    type: str | None = None  # primary, secondary, tertiary
    level: int | None = None  # 1, 2, 3
    parent: str | None = None
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_category_codes(cls, data: Any) -> Any:
        """Normalize category codes from either flat or nested format."""
        if isinstance(data, dict):
            # If we have flat mcc/sic/naics but no code object, create one
            if "code" not in data and any(k in data for k in ("mcc", "sic", "naics")):
                data["code"] = {
                    "mcc": data.get("mcc"),
                    "sic": data.get("sic"),
                    "naics": data.get("naics"),
                }
            # If we have a code object, also set flat fields for convenience
            elif "code" in data and isinstance(data["code"], dict):
                data["mcc"] = data.get("mcc") or data["code"].get("mcc")
                data["sic"] = data.get("sic") or data["code"].get("sic")
                data["naics"] = data.get("naics") or data["code"].get("naics")
        return data

    def get_mcc(self) -> int | None:
        """Get MCC code from either format."""
        if self.code and self.code.mcc:
            return self.code.mcc
        return self.mcc

    def get_sic(self) -> int | None:
        """Get SIC code from either format."""
        if self.code and self.code.sic:
            return self.code.sic
        return self.sic

    def get_naics(self) -> int | None:
        """Get NAICS code from either format."""
        if self.code and self.code.naics:
            return self.code.naics
        return self.naics


class CategoryStructure(BaseModel):
    """Hierarchical category structure."""

    primary: Category
    secondary: Category | None = None
    tertiary: Category | None = None
    confidence: int = Field(default=0, ge=0, le=100)


class Subscription(BaseModel):
    """Subscription detection result."""

    recurring: bool
    type: SubscriptionType | None = None


class StructuredAddress(BaseModel):
    """Structured address information."""

    street: str | None = None
    city: str | None = None
    state: str | None = None
    postalCode: str | None = None
    country: str | None = None
    countryName: str | None = None
    coordinates: Coordinates | None = None
    timezone: str | None = None


class ConfidenceWithReasons(BaseModel):
    """Confidence score with explanatory reason tags (v1.1.0+)."""

    value: int = Field(default=0, ge=0, le=100, description="Confidence score (0-100)")
    reasons: list[str] = Field(default_factory=list, description="Tags explaining the confidence score")


class LocationRating(BaseModel):
    """Location rating information."""

    average: float | None = None
    count: int | None = None
    source: str | None = None


# Entity Data Models


class MerchantData(BaseModel):
    """Merchant information."""

    id: str | None = None
    name: str
    alias: list[str] = []
    keywords: list[str] | None = None
    icon: str | None = None
    description: str | None = None
    color: str | None = None
    website: str | None = None
    domain: str | None = None


class LocationData(BaseModel):
    """Location information."""

    id: str | None = None
    name: str | None = None
    formatted: str | None = None
    phoneNumber: str | None = None
    website: str | None = None
    priceRange: str | None = None
    rating: LocationRating | None = None
    structured: StructuredAddress | None = None


class IntermediaryData(BaseModel):
    """Intermediary information (payment processors, platforms, wallets, P2P services).

    Replaces the old separate PaymentProcessorData and P2PPlatformInfo models.
    Roles: processor, platform, wallet, p2p.
    """

    id: str | None = None
    name: str
    icon: str | None = None
    description: str | None = None
    color: str | None = None
    website: str | None = None
    domain: str | None = None


class PersonData(BaseModel):
    """Person information (P2P transfer recipients)."""

    displayName: str


# Entity Result (v1.1.0 entities array pattern)


class EntityResult(BaseModel):
    """An enriched entity from the entities array.

    Each entity has a type, role, confidence (with reasons), and type-specific data.
    Only identified entities are included -- no "status: no_match" entries.
    """

    type: str = Field(..., description="Entity type: merchant, location, intermediary, person")
    role: str = Field(..., description="Contextual role (e.g. organization, store_location, processor, recipient)")
    confidence: ConfidenceWithReasons = Field(default_factory=ConfidenceWithReasons)
    data: dict[str, Any] = Field(default_factory=dict)

    def get_name(self) -> str | None:
        """Get the primary display name from entity data, regardless of type."""
        if self.type == EntityType.PERSON:
            return self.data.get("displayName")
        return self.data.get("name")

    def as_merchant(self) -> MerchantData | None:
        """Parse data as MerchantData if this is a merchant entity."""
        if self.type == EntityType.MERCHANT:
            return MerchantData.model_validate(self.data)
        return None

    def as_location(self) -> LocationData | None:
        """Parse data as LocationData if this is a location entity."""
        if self.type == EntityType.LOCATION:
            return LocationData.model_validate(self.data)
        return None

    def as_intermediary(self) -> IntermediaryData | None:
        """Parse data as IntermediaryData if this is an intermediary entity."""
        if self.type == EntityType.INTERMEDIARY:
            return IntermediaryData.model_validate(self.data)
        return None

    def as_person(self) -> PersonData | None:
        """Parse data as PersonData if this is a person entity."""
        if self.type == EntityType.PERSON:
            return PersonData.model_validate(self.data)
        return None


# Transaction & Enrichment Data


class TransactionData(BaseModel):
    """Enriched transaction data."""

    model_config = {"extra": "allow"}

    category: Any = None
    subscription: Subscription | None = None
    channel: TransactionChannel | str = TransactionChannel.UNKNOWN
    confidence: ConfidenceWithReasons = Field(default_factory=ConfidenceWithReasons)

    @model_validator(mode="before")
    @classmethod
    def normalize_transaction_data(cls, data: Any) -> Any:
        """Normalize transaction data from API response."""
        if isinstance(data, dict):
            # Handle channel as string
            if "channel" in data and isinstance(data["channel"], str):
                try:
                    data["channel"] = TransactionChannel(data["channel"])
                except ValueError:
                    data["channel"] = TransactionChannel.UNKNOWN
            # Handle confidence as plain int (backward compat) or as object
            if "confidence" in data and isinstance(data["confidence"], int):
                data["confidence"] = {"value": data["confidence"], "reasons": []}
        return data

    @property
    def category_structure(self) -> CategoryStructure | None:
        """Get category as a CategoryStructure if possible."""
        if self.category is None:
            return None
        if isinstance(self.category, CategoryStructure):
            return self.category
        if isinstance(self.category, dict):
            try:
                if "primary" in self.category:
                    return CategoryStructure.model_validate(self.category)
                elif "name" in self.category:
                    return CategoryStructure(
                        primary=Category.model_validate(self.category),
                        confidence=self.category.get("confidence", 0),
                    )
            except Exception:
                pass
        return None

    def get_primary_category_name(self) -> str:
        """Safely get the primary category name."""
        if self.category is None:
            return "Unknown"

        if isinstance(self.category, CategoryStructure):
            return self.category.primary.name

        if isinstance(self.category, dict):
            if "primary" in self.category:
                primary = self.category["primary"]
                if isinstance(primary, dict):
                    return primary.get("name", "Unknown")
                if isinstance(primary, Category):
                    return primary.name
            if "name" in self.category:
                return self.category["name"]

        return "Unknown"

    def get_confidence_value(self) -> int:
        """Get the numeric confidence value."""
        if isinstance(self.confidence, ConfidenceWithReasons):
            return self.confidence.value
        return 0


class EnrichmentData(BaseModel):
    """Complete enrichment data (v1.1.0 entities array pattern)."""

    transaction: TransactionData
    entities: list[EntityResult] = Field(default_factory=list)

    def find_entity(self, entity_type: str) -> EntityResult | None:
        """Find the first entity of a given type."""
        return next((e for e in self.entities if e.type == entity_type), None)

    def find_entities(self, entity_type: str) -> list[EntityResult]:
        """Find all entities of a given type."""
        return [e for e in self.entities if e.type == entity_type]

    @property
    def merchant(self) -> EntityResult | None:
        """Get the merchant entity, if present."""
        return self.find_entity(EntityType.MERCHANT)

    @property
    def location(self) -> EntityResult | None:
        """Get the location entity, if present."""
        return self.find_entity(EntityType.LOCATION)

    @property
    def intermediary(self) -> EntityResult | None:
        """Get the first intermediary entity, if present."""
        return self.find_entity(EntityType.INTERMEDIARY)

    @property
    def person(self) -> EntityResult | None:
        """Get the person entity, if present."""
        return self.find_entity(EntityType.PERSON)

    def get_merchant_name(self) -> str | None:
        """Convenience: get the merchant display name."""
        merchant = self.merchant
        return merchant.get_name() if merchant else None

    def get_intermediary_name(self) -> str | None:
        """Convenience: get the intermediary display name."""
        intermediary = self.intermediary
        return intermediary.get_name() if intermediary else None

    def get_person_name(self) -> str | None:
        """Convenience: get the person display name."""
        person = self.person
        return person.get_name() if person else None


class ResponseMeta(BaseModel):
    """Response metadata."""

    generatedAt: datetime
    requestId: str
    version: str
    categoryVersion: str | None = None
    errors: list[str] | None = None


class EnrichSuccessResponse(BaseModel):
    """Successful enrichment response."""

    success: bool
    partial: bool
    data: EnrichmentData
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    """Error details."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool
    error: ErrorDetail
    meta: ResponseMeta


class RateLimitInfo(BaseModel):
    """Rate limit information from response headers (API v1.1.2).

    The API uses a token-bucket RPS limit combined with a hard concurrency cap.
    Both dimensions can independently trigger a 429; the active one is indicated
    by X-RateLimit-Scope.  Retry-After is in **seconds**.
    """

    # RPS bucket
    limit: int | None = None
    remaining: int | None = None
    reset: str | None = None

    # Concurrency cap
    scope: str | None = None                    # "rps" or "concurrency"
    concurrency_limit: int | None = None
    concurrency_remaining: int | None = None

    # Retry-After header (seconds, present on 429 and 503)
    retry_after_seconds: int | None = None

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> RateLimitInfo:
        """Parse rate limit info from response headers."""
        def _int(key: str) -> int | None:
            try:
                v = int(headers.get(key, 0))
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        return cls(
            limit=_int("X-RateLimit-Limit"),
            remaining=_int("X-RateLimit-Remaining"),
            reset=headers.get("X-RateLimit-Reset") or None,
            scope=headers.get("X-RateLimit-Scope") or None,
            concurrency_limit=_int("X-RateLimit-Concurrency-Limit"),
            concurrency_remaining=_int("X-RateLimit-Concurrency-Remaining"),
            retry_after_seconds=_int("Retry-After"),
        )

    def get_reset_timestamp(self) -> float | None:
        """Parse the ISO reset timestamp to a Unix timestamp for comparison."""
        if not self.reset:
            return None
        try:
            return datetime.fromisoformat(self.reset.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            return None

    def get_retry_after_seconds(self) -> float | None:
        """Return the Retry-After wait in seconds (already in seconds per spec)."""
        return float(self.retry_after_seconds) if self.retry_after_seconds else None


class EnrichmentResult(BaseModel):
    """Combined result with input transaction and enrichment."""

    input: Transaction
    success: bool
    partial: bool = False
    data: EnrichmentData | None = None
    error: ErrorDetail | None = None
    request_id: str | None = None
    processing_time_ms: float | None = None
