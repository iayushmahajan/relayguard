"""Idempotent baseline seed command for RelayGuard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Integration, Role
from app.db.session import get_async_sessionmaker

BASELINE_ROLES = ("admin", "operator", "viewer")
BASELINE_INTEGRATIONS = (
    ("github-sandbox", "GitHub Sandbox"),
    ("stripe-sandbox", "Stripe Sandbox"),
)


@dataclass(frozen=True)
class SeedResult:
    """Summary of created seed records."""

    roles_created: int
    integrations_created: int


async def seed_database(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> SeedResult:
    """Create baseline seed records when absent without modifying existing rows."""
    resolved_session_factory = session_factory or get_async_sessionmaker()
    roles_created = 0
    integrations_created = 0

    async with resolved_session_factory() as session:
        async with session.begin():
            for role_name in BASELINE_ROLES:
                role_exists = await session.scalar(select(Role.id).where(Role.name == role_name))
                if role_exists is None:
                    session.add(Role(name=role_name))
                    roles_created += 1

            for slug, name in BASELINE_INTEGRATIONS:
                integration_exists = await session.scalar(
                    select(Integration.id).where(Integration.slug == slug)
                )
                if integration_exists is None:
                    session.add(
                        Integration(
                            name=name,
                            slug=slug,
                            enabled=False,
                            status="disabled",
                        )
                    )
                    integrations_created += 1

    return SeedResult(roles_created=roles_created, integrations_created=integrations_created)


async def async_main() -> None:
    """Run the seed command."""
    result = await seed_database()
    print(
        "Seed complete: "
        f"roles_created={result.roles_created} "
        f"integrations_created={result.integrations_created}"
    )


def main() -> None:
    """Synchronous command wrapper."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
