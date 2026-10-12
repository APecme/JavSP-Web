"""Isolated, synthetic credential and account-lifecycle regression probes."""
from pathlib import Path
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / "vendor" / "JavSP"))


def run():
    with tempfile.TemporaryDirectory(prefix="security-data-", dir=ROOT) as temporary:
        os.environ["JAVSP_WEB_DATA_DIR"] = temporary
        os.environ["JAVSP_VENDOR_DIR"] = str(SOURCE / "vendor" / "JavSP")
        from fastapi.testclient import TestClient
        from javsp_web import storage, tasks
        with patch("threading.Thread.start"), patch.object(tasks, "recover_interrupted_tasks"):
            from javsp_web import server
        import yaml
        report = {}
        admin = TestClient(server.app)
        operator = TestClient(server.app)
        anonymous = TestClient(server.app)
        assert admin.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        assert admin.post("/api/users", json={"username": "auditoperator", "password": "initial-operator-password", "password_confirm": "initial-operator-password", "role": "operator"}).status_code == 200
        assert operator.post("/api/auth/login", json={"username": "auditoperator", "password": "initial-operator-password"}).status_code == 200

        config = yaml.safe_load(storage.read_config())
        config["translator"]["engine"] = {"name": "openai", "url": "https://translator.invalid/v1/chat/completions", "model": "audit", "api_key": "SYNTHETIC_TRANSLATOR_SECRET"}
        config["network"]["proxy_server"] = "http://audit-user:SYNTHETIC_PROXY_PASSWORD@proxy.invalid:8080"
        storage.write_config(yaml.safe_dump(config))
        preset = storage.get_preset("default")
        preset.update(form=config, content=yaml.safe_dump(config))
        storage.save_preset(preset)
        secret_responses = []
        for route in ("/api/config", "/api/presets"):
            response = operator.get(route)
            secret_responses.append({"route": route, "http": response.status_code,
                                     "translator_secret_visible": "SYNTHETIC_TRANSLATOR_SECRET" in response.text,
                                     "proxy_password_visible": "SYNTHETIC_PROXY_PASSWORD" in response.text})
            assert response.status_code == 200
            assert "SYNTHETIC_TRANSLATOR_SECRET" in response.text
            assert "SYNTHETIC_PROXY_PASSWORD" in response.text
        report["operator_secret_read"] = secret_responses

        reset = admin.put("/api/users/auditoperator", json={"username": "auditoperator", "password": "replacement-password", "password_confirm": "replacement-password", "role": "operator"})
        old_session = operator.get("/api/auth/me")
        old_login = anonymous.post("/api/auth/login", json={"username": "auditoperator", "password": "initial-operator-password"})
        assert reset.status_code == 200 and old_session.status_code == 200 and old_login.status_code == 401
        report["password_reset_session"] = {"reset_http": reset.status_code, "old_password_login_http": old_login.status_code, "old_session_http": old_session.status_code}

        removed = admin.delete("/api/users/auditoperator")
        deleted_session = operator.get("/api/auth/me")
        recreated = admin.post("/api/users", json={"username": "auditoperator", "password": "unrelated-new-admin-password", "password_confirm": "unrelated-new-admin-password", "role": "admin"})
        revived_session = operator.get("/api/auth/me")
        privileged_request = operator.get("/api/users")
        assert removed.status_code == 200 and deleted_session.status_code == 401
        assert recreated.status_code == 200 and revived_session.status_code == 200
        assert revived_session.json()["role"] == "admin" and privileged_request.status_code == 200
        report["deleted_username_reuse"] = {"delete_http": removed.status_code, "session_while_deleted_http": deleted_session.status_code,
                                           "recreate_http": recreated.status_code, "old_session_after_recreate": revived_session.json(), "admin_api_http": privileged_request.status_code}

        assert admin.put("/api/users/admin", json={"username": "admin", "password": "hardened-admin-password", "password_confirm": "hardened-admin-password", "role": "admin"}).status_code == 200
        before_corruption = anonymous.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        storage.USERS_FILE.write_text('{"truncated":', encoding="utf-8")
        after_corruption = anonymous.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert before_corruption.status_code == 401 and after_corruption.status_code == 200
        users_after = storage.list_users()
        assert len(users_after) == 1 and users_after[0]["username"] == "admin"
        report["corrupt_user_store"] = {"default_password_before_corruption_http": before_corruption.status_code,
                                        "default_password_after_corruption_http": after_corruption.status_code,
                                        "accounts_after_corruption": [item["username"] for item in users_after]}

        for client in (admin, operator, anonymous):
            client.close()
        result = ROOT / "security-repro-results.json"
        result.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
