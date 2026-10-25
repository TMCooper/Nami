# Readiness of the scraper APIs (set by backend.main), exposed to the UI through /api/catalog/status
api_ready = {"animesama": False, "voiranime": False}


def all_ready() -> bool:
    return all(api_ready.values())
