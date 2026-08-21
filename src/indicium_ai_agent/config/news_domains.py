NEWS_DOMAIN_ALLOWLIST: dict[str, list[str]] = {
    "tier1_authoritative": [
        "fiocruz.br",
        "agencia.fiocruz.br",
        "gov.br",
    ],
    "tier2_journalism": [
        "agenciabrasil.ebc.com.br",
        "g1.globo.com",
        "uol.com.br",
        "folha.uol.com.br",
        "estadao.com.br",
    ],
    "tier3_international": [
        "paho.org",
    ],
}


def get_all_domains() -> list[str]:
    domains: list[str] = []
    for tier in NEWS_DOMAIN_ALLOWLIST.values():
        domains.extend(tier)
    return domains
