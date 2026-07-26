"""Integrity checks for the site-rules table."""

from playfix.sites import SITES, iter_domains


def test_rules_present() -> None:
    assert len(SITES) >= 10


def test_ids_unique() -> None:
    ids = [rule.id for rule in SITES]
    assert len(ids) == len(set(ids))


def test_domains_unique_across_rules() -> None:
    domains = [d for d, _ in iter_domains()]
    assert len(domains) == len(set(domains)), "a domain is claimed by two rules"


def test_fields_well_formed() -> None:
    for rule in SITES:
        assert rule.id and rule.id.islower()
        assert rule.name
        assert rule.domains, f"{rule.id} has no source domains"
        assert "." in rule.fix_domain, f"{rule.id} fix_domain looks wrong"
        assert rule.fix_domain not in rule.domains, f"{rule.id} maps to itself"
        for domain in rule.domains:
            assert "." in domain and " " not in domain
