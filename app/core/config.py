
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    )
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "15")
    )
    # Development-only: return reset token in API response because no email provider is configured.
    RESET_TOKEN_EXPOSE: bool = os.getenv("RESET_TOKEN_EXPOSE", "false").lower() == "true"

    def validate(self):
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY is missing in .env")


settings = Settings()
settings.validate()
