import json
import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "staging", "prod"] = "dev"

    database_url: str

    meta_app_id: str
    meta_app_secret: str
    webhook_verify_token: str
    graph_version: str = "v23.0"

    kms_key_id: str
    sqs_queue_url: str
    aws_region: str = "us-east-1"
    # Set for local dev against LocalStack; left unset in prod so boto3 uses real AWS endpoints.
    aws_endpoint_url: str | None = None

    @property
    def graph_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.graph_version}"


def _hydrate_from_secrets_manager() -> None:
    """In Lambda, Terraform wires DATABASE_URL_SECRET / META_APP_SECRET_ARN (Secrets Manager
    ARNs) instead of plaintext values — see infra/terraform/modules/lambda_api|lambda_worker.
    Resolve them into the plain env vars Settings expects, once per cold start. Local dev never
    sets these ARNs, so this is a no-op outside Lambda."""
    db_secret_arn = os.environ.get("DATABASE_URL_SECRET")
    meta_secret_arn = os.environ.get("META_APP_SECRET_ARN")
    if not db_secret_arn and not meta_secret_arn:
        return

    import boto3

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    if db_secret_arn and "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = client.get_secret_value(SecretId=db_secret_arn)["SecretString"]

    if meta_secret_arn and "META_APP_ID" not in os.environ:
        # JSON blob: {"meta_app_id": ..., "meta_app_secret": ..., "webhook_verify_token": ...}
        # populated via `aws secretsmanager put-secret-value` after Meta app setup (SPEC §7).
        meta = json.loads(client.get_secret_value(SecretId=meta_secret_arn)["SecretString"])
        os.environ["META_APP_ID"] = meta["meta_app_id"]
        os.environ["META_APP_SECRET"] = meta["meta_app_secret"]
        os.environ["WEBHOOK_VERIFY_TOKEN"] = meta["webhook_verify_token"]


@lru_cache
def get_settings() -> Settings:
    _hydrate_from_secrets_manager()
    return Settings()  # type: ignore[call-arg]  # fields are populated from the environment
