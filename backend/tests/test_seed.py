from app.commands.seed import BASELINE_INTEGRATIONS, BASELINE_ROLES


def test_seed_baseline_scope_is_limited() -> None:
    assert BASELINE_ROLES == ("admin", "operator", "viewer")
    assert BASELINE_INTEGRATIONS == (
        ("github-sandbox", "GitHub Sandbox"),
        ("stripe-sandbox", "Stripe Sandbox"),
    )
