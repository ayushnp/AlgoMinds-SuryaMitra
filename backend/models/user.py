from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, GetCoreSchemaHandler
from pydantic.json_schema import JsonSchemaValue # This is correct for V2 JSON schema return type
from bson import ObjectId
from pydantic_core import core_schema


# --- MongoDB ObjectId Custom Type (CORRECTED FINAL VERSION) ---

class PyObjectId(ObjectId):
    """
    Custom type to handle mapping between MongoDB's ObjectId and Pydantic string/validation.
    """

    @classmethod
    def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        We must validate PyObjectId as a string that can be parsed into an ObjectId.
        """
        return core_schema.union_schema([
            # check if it's an instance of this class (i.e. an ObjectId already)
            core_schema.is_instance_schema(ObjectId),
            # check if it's a string that can be converted to an ObjectId
            core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls.validate),
            ])
        ],
            # FIX HERE: Renamed serializer function for Pydantic V2 compatibility
            serialization=core_schema.to_string_ser_schema(), # <-- This function name is correct
        )

    @classmethod
    def validate(cls, value: str) -> ObjectId:
        """Custom validator to ensure the string is a valid MongoDB ObjectId."""
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId format")
        return ObjectId(value)

    @classmethod
    def __get_pydantic_json_schema__(
            cls, core_schema: core_schema.CoreSchema, handler: GetCoreSchemaHandler
    ) -> JsonSchemaValue:
        """Tells Pydantic to represent this type as a string in the generated OpenAPI schema."""

        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema['type'] = 'string'

        return json_schema


# --- User Base Models ---

class UserModel(BaseModel):
    """Base model for a user in the database."""
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    email: EmailStr
    hashed_password: str
    full_name: str
    phone_number: str
    is_active: bool = True

    class Config:
        # Pydantic V2 Note: 'orm_mode' is deprecated, use 'from_attributes=True'
        # 'allow_population_by_field_name' is deprecated, use 'validate_by_name=True'
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        orm_mode = True


# The rest of the models are already V2 compatible
class UserCreate(BaseModel):
    """Model for user registration input."""
    email: EmailStr
    password: str
    full_name: str
    phone_number: str


class UserLogin(BaseModel):
    """Model for user login input."""
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """Model for user output (excludes sensitive info like password hash)."""
    id: str = Field(alias="_id")
    email: EmailStr
    full_name: str

    class Config:
        json_encoders = {ObjectId: str}
        orm_mode = True