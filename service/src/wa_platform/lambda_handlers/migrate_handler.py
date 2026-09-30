from alembic import command
from alembic.config import Config

from wa_platform.core.config import get_settings
from wa_platform.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def handler(event: dict, context) -> dict:
    """Invoked manually or by the deploy workflow (`aws lambda invoke`) to run migrations
    against RDS from inside the VPC — the CI runner itself has no network path to the private
    subnet RDS lives in. Runs in the same package as the API/worker Lambdas (`make package`
    bundles alembic.ini + migrations/ alongside the app code for this reason)."""
    settings = get_settings()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)

    log.info("migration_starting")
    command.upgrade(cfg, "head")
    log.info("migration_complete")
    return {"ok": True}
