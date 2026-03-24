def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
    assert r.json()["rows_loaded"] == 1


def test_field_values(client):
    r = client.get("/api/field-values")
    assert r.status_code == 200
    data = r.json()
    assert "underwriting" in data
    assert data["underwriting"][0]["value"] == "NMORI"
    assert data["underwriting"][0]["label"] == "No Moratorium"


def test_mappings_pagination(client):
    r = client.get("/api/mappings?page=1&page_size=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["rows"]) == 1


def test_mappings_filter_by_label(client):
    r = client.get("/api/mappings?filter=28+days")
    assert r.status_code == 200
    assert r.json()["total"] == 1  # test row has psych=1a ("28 days")


def test_mappings_filter_by_code(client):
    r = client.get("/api/mappings?filter=1a")
    assert r.status_code == 200
    assert r.json()["total"] == 1  # dalecode and psych value both contain "1a"


def test_resolve(client):
    r = client.post("/api/resolve", json={
        "underwriting": "NMORI", "corecover": "Y",   "psych": "1a",
        "gpreferred":   "2a",    "hospital_list": "3a", "opticaldental": "4a",
        "sixweek":      "5a",    "excess": "6a",      "benefitreduction": "7a",
        "oplimit":      "8a",    "islands": "9a",
    })
    assert r.status_code == 200
    assert r.json()["plancode"] == "TST"


def test_resolve_invalid_value(client):
    r = client.post("/api/resolve", json={
        "underwriting": "INVALID", "corecover": "Y",   "psych": "1a",
        "gpreferred":   "2a",      "hospital_list": "3a", "opticaldental": "4a",
        "sixweek":      "5a",      "excess": "6a",      "benefitreduction": "7a",
        "oplimit":      "8a",      "islands": "9a",
    })
    assert r.status_code == 422


def test_dalecode_lookup(client):
    r = client.post("/api/dalecode-lookup", json={"dalecode": "NMORIY1a2a3a4a5a6a7a8a9a"})
    assert r.status_code == 200
    data = r.json()
    assert data["plancode"] == "TST"
    assert any(f["field"] == "psych" and f["label"] == "28 days" for f in data["fields"])


def test_dalecode_lookup_invalid(client):
    r = client.post("/api/dalecode-lookup", json={"dalecode": "NOTVALID"})
    assert r.status_code == 404
