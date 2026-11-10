import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class WalletCreateModel(BaseModel):
    address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    user_id: uuid.UUID
    is_verified: bool = False
    

class WalletModel(BaseModel):
    id: uuid.UUID
    address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    user_id: uuid.UUID
    is_verified: bool
    created_at: datetime
    updated_at: datetime