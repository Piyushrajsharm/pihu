"""
Tests for api/governance.py — Policy engine, budget, safety, tool permissions.
"""
import pytest
import os

os.environ["PIHU_ENV"] = "testing"

from api.governance import GovernanceEngine


@pytest.fixture
def engine():
    return GovernanceEngine()


class TestCommandSafety:
    def test_safe_command_passes(self, engine):
        engine.check_command_safety("list all files")  # Should not raise

    def test_rm_rf_blocked(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            engine.check_command_safety("rm -rf /")
        assert exc_info.value.status_code == 403

    def test_drop_database_blocked(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            engine.check_command_safety("DROP DATABASE production;")
        assert exc_info.value.status_code == 403

    def test_format_c_blocked(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            engine.check_command_safety("format C:")

    def test_shutdown_blocked(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            engine.check_command_safety("shutdown /s /t 0")

    def test_mixed_case_still_caught(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            engine.check_command_safety("RM -RF /")


class TestExecutionBudget:
    def test_budget_within_limit(self, engine):
        engine.check_execution_budget("user1", estimated_cost=100)  # Should pass

    def test_budget_exceeded_raises(self, engine):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            engine.check_execution_budget("user1", estimated_cost=999_999_999)
        assert exc_info.value.status_code == 403


class TestToolPermissions:
    def test_default_tools_allowed(self, engine):
        # Default policy should allow common tools
        # Signature: check_tool_permission(tool_name: str, role: str)
        result = engine.check_tool_permission("web_search", "member")
        assert result is True or result is None  # Either True or no restriction

    def test_full_check_returns_dict(self, engine):
        result = engine.full_check(
            tenant_id="test_user",
            role="admin",
            tool_name="web_search",
            command="search for weather",
            estimated_cost=50
        )
        assert isinstance(result, dict)
        assert "approved" in result
