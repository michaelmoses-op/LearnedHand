import uuid
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.schemas.common import StrictModel

Password = Annotated[str, Field(min_length=12, max_length=128)]
Token = Annotated[str, StringConstraints(min_length=10, max_length=200)]


class Credentials(StrictModel):
    email: EmailStr = Field(max_length=254)
    password: Password

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class LoginRequest(StrictModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class EmailRequest(StrictModel):
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class TokenRequest(StrictModel):
    token: Token


class PasswordResetConfirm(StrictModel):
    token: Token
    new_password: Password


class UserOut(StrictModel):
    id: uuid.UUID
    email: str
    email_verified: bool


class Accepted(StrictModel):
    status: str = "accepted"
    email_verification_required: bool = True
