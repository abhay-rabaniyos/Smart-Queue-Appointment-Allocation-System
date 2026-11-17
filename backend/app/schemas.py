from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Registration(StrictModel):
    service_id: str
    name: str = Field(min_length=2, max_length=100)
    contact: str = Field(default="", max_length=254)
    channel: Literal["email", "sms", "whatsapp"] = "email"
    source: Literal["appointment", "walk_in"] = "walk_in"
    slot: datetime | None = None
    priority: int = Field(default=0, ge=0, le=2)

    @field_validator("slot")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Include timezone offset")
        return value

    @model_validator(mode="after")
    def valid_contact(self):
        if self.contact:
            if self.channel == "email":
                from pydantic import TypeAdapter

                TypeAdapter(EmailStr).validate_python(self.contact)
            elif not (
                self.contact.startswith("+")
                and self.contact[1:].isdigit()
                and 8 <= len(self.contact[1:]) <= 15
            ):
                raise ValueError("Use an international phone number, e.g. +919876543210")
        if (self.source == "appointment") != (self.slot is not None):
            raise ValueError("Appointments require a slot; walk-ins cannot specify one")
        return self


class Reschedule(StrictModel):
    slot: datetime

    @field_validator("slot")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include timezone offset")
        return value


class Login(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class StaffInput(StrictModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "receptionist", "staff"]


class StaffUpdate(StrictModel):
    active: bool


class CounterInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    service_id: str
    staff_id: str | None = None
    active: bool = True


class ServiceInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    minutes: int = Field(default=10, ge=1, le=120)
    capacity: int = Field(default=2, ge=1, le=100)
    active: bool = True


class RulesInput(StrictModel):
    aging_minutes: int = Field(ge=1, le=120)
    priority_weight: int = Field(ge=1, le=120)
    grace_minutes: int = Field(ge=1, le=120)
