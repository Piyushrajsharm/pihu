"""
Pihu — Tool Broker
The ONLY component allowed to invoke tools. Sits between the Router
and all execution engines, enforcing policy on every invocation.

Flow:
  Router → ToolBroker.execute(action, resource, ...) 
           → PolicyEngine.evaluate(request)
           → Decision routing:
               ALLOW → execute tool, record result
               DENY → return denial to Router
               REQUIRE_APPROVAL → prompt user, then execute or deny
               REQUIRE_SANDBOX → route to DockerExecutor
               REQUIRE_DRY_RUN → preview without execution
           → AuditLog.record(request, decision, result)
"""

import time
from typing import Optional, Any, Generator
from dataclasses import dataclass, field

from logger import get_logger

log = get_logger("BROKER")


@dataclass
class ToolResult:
    """Result of a brokered tool invocation."""
    action: str
    success: bool
    output: Any
    denied: bool = False
    denial_reason: str = ""
    approval_requested: bool = False
    approval_granted: Optional[bool] = None
    sandboxed: bool = False
    dry_run: bool = False
    risk_score: float = 0.0
    correlation_id: str = ""
    elapsed_ms: float = 0.0


class ToolBroker:
    """
    Centralized tool invocation gateway.
    
    NOTHING executes without going through here.
    The LLM proposes actions. The ToolBroker authorizes them.
    """

    def __init__(self, policy_engine=None, audit_log=None, session_trust=None,
                 approval_callback=None):
        """
        Args:
            policy_engine: PolicyEngine instance
            audit_log: AuditLog instance for recording decisions
            session_trust: SessionTrustManager instance
            approval_callback: Callable that prompts user for approval.
                              Signature: callback(prompt_message: str) -> bool
                              If None, all approval-required actions are denied.
        """
        self.policy_engine = policy_engine
        self.audit = audit_log
        self.session_trust = session_trust
        self._approval_callback = approval_callback
        
        # Stats
        self._total_requests = 0
        self._total_allowed = 0
        self._total_denied = 0
        self._total_approvals = 0
        
        log.info("🔧 ToolBroker initialized | policy=%s | audit=%s | approvals=%s",
                 "ACTIVE" if policy_engine else "NONE",
                 "ACTIVE" if audit_log else "NONE",
                 "CLI" if approval_callback else "AUTO-DENY")

    def execute(
        self,
        action: str,
        resource_path: Optional[str] = None,
        resource_url: Optional[str] = None,
        resource_command: Optional[str] = None,
        resource_description: str = "",
        user_id: str = "pihu_user",
        tool_fn: Any = None,
        tool_args: dict = None,
        tool_kwargs: dict = None,
        chain_depth: int = 0,
    ) -> ToolResult:
        """
        Execute a tool invocation through the full policy pipeline.
        
        Args:
            action: ActionType string value (e.g., "read_file", "shell_exec")
            resource_path: File path being accessed (if applicable)
            resource_url: URL being accessed (if applicable)
            resource_command: Shell command (if applicable)
            resource_description: Human-readable description
            user_id: Who is making the request
            tool_fn: The actual function to call if approved
            tool_args: Positional arguments for tool_fn
            tool_kwargs: Keyword arguments for tool_fn
            chain_depth: Current depth in nested tool calls
            
        Returns:
            ToolResult with execution outcome
        """
        t0 = time.time()
        self._total_requests += 1
        
        from security.policy_engine import (
            PolicyRequest, Subject, Resource, PolicyContext,
            ActionType, Verdict,
        )
        
        # Build policy request
        try:
            action_type = ActionType(action)
        except ValueError:
            action_type = ActionType.SHELL_EXEC  # Unknown = high risk
        
        trust_level = 1  # Default ASSIST
        if self.session_trust:
            trust_level = int(self.session_trust.current_level)
        
        request = PolicyRequest(
            subject=Subject(
                user_id=user_id,
                trust_level=trust_level,
            ),
            action=action_type,
            resource=Resource(
                path=resource_path,
                url=resource_url,
                command=resource_command,
                description=resource_description or action,
            ),
            context=PolicyContext(
                request_chain_depth=chain_depth,
            ),
        )
        
        # Evaluate policy
        if self.policy_engine:
            decision = self.policy_engine.evaluate(request)
        else:
            # No policy engine = fail-open with warning
            log.warning("⚠️ No PolicyEngine attached — fail-open mode")
            from security.policy_engine import PolicyDecision, Verdict
            decision = PolicyDecision(
                verdict=Verdict.ALLOW,
                reason="No policy engine — fail-open",
                matched_rules=["no_policy"],
                risk_score=0.5,
                correlation_id=request.context.correlation_id,
            )
        
        cid = decision.correlation_id
        
        # Route based on verdict
        if decision.verdict == Verdict.DENY:
            self._total_denied += 1
            self._record_audit("DENIED", action, decision)
            
            elapsed = (time.time() - t0) * 1000
            log.warning("🚫 [%s] DENIED: %s | %s", cid, action, decision.reason)
            
            return ToolResult(
                action=action,
                success=False,
                output=None,
                denied=True,
                denial_reason=decision.reason,
                risk_score=decision.risk_score,
                correlation_id=cid,
                elapsed_ms=elapsed,
            )
        
        if decision.verdict == Verdict.REQUIRE_APPROVAL:
            self._total_approvals += 1
            
            approved = self._request_approval(decision)
            
            if not approved:
                self._total_denied += 1
                self._record_audit("APPROVAL_DENIED", action, decision)
                
                elapsed = (time.time() - t0) * 1000
                log.info("❌ [%s] Approval denied for: %s", cid, action)
                
                return ToolResult(
                    action=action,
                    success=False,
                    output=None,
                    denied=True,
                    denial_reason="User denied approval",
                    approval_requested=True,
                    approval_granted=False,
                    risk_score=decision.risk_score,
                    correlation_id=cid,
                    elapsed_ms=(time.time() - t0) * 1000,
                )
            
            # Escalate session trust if needed
            if self.session_trust and decision.requires_user_prompt:
                from security.session_trust import TrustLevel
                required = ACTION_TRUST_REQUIREMENTS = {
                    "read_file": 1, "write_file": 2, "delete_file": 2,
                    "run_python": 3, "shell_exec": 4, "call_api": 4,
                }.get(action, 2)
                if trust_level < required:
                    self.session_trust.escalate(TrustLevel(required))
            
            log.info("✅ [%s] Approval granted for: %s", cid, action)
        
        if decision.verdict == Verdict.REQUIRE_DRY_RUN:
            self._record_audit("DRY_RUN", action, decision)
            
            # Execute in dry-run mode
            elapsed = (time.time() - t0) * 1000
            return ToolResult(
                action=action,
                success=True,
                output=f"[DRY RUN] Would execute: {action} on {resource_description}",
                dry_run=True,
                risk_score=decision.risk_score,
                correlation_id=cid,
                elapsed_ms=elapsed,
            )
        
        # ── EXECUTE THE TOOL ──
        sandboxed = decision.verdict == Verdict.REQUIRE_SANDBOX
        
        try:
            if tool_fn:
                args = tool_args or ()
                kwargs = tool_kwargs or {}
                
                # Touch session (activity tracking)
                if self.session_trust:
                    self.session_trust.touch()
                
                result = tool_fn(*args, **kwargs) if not isinstance(args, dict) else tool_fn(**args, **kwargs)
                
                self._total_allowed += 1
                self._record_audit("EXECUTED", action, decision, success=True)
                
                elapsed = (time.time() - t0) * 1000
                log.info("✅ [%s] %s executed successfully (%.0fms)", cid, action, elapsed)
                
                return ToolResult(
                    action=action,
                    success=True,
                    output=result,
                    sandboxed=sandboxed,
                    risk_score=decision.risk_score,
                    correlation_id=cid,
                    elapsed_ms=elapsed,
                    approval_requested=decision.verdict == Verdict.REQUIRE_APPROVAL,
                    approval_granted=True if decision.verdict == Verdict.REQUIRE_APPROVAL else None,
                )
            else:
                # No tool function provided — just return the decision
                self._total_allowed += 1
                elapsed = (time.time() - t0) * 1000
                return ToolResult(
                    action=action,
                    success=True,
                    output=decision,
                    sandboxed=sandboxed,
                    risk_score=decision.risk_score,
                    correlation_id=cid,
                    elapsed_ms=elapsed,
                )
        
        except Exception as e:
            self._record_audit("EXECUTION_FAILED", action, decision, success=False, error=str(e))
            
            elapsed = (time.time() - t0) * 1000
            log.error("💥 [%s] Tool execution failed: %s | %s", cid, action, e)
            
            return ToolResult(
                action=action,
                success=False,
                output=str(e),
                sandboxed=sandboxed,
                risk_score=decision.risk_score,
                correlation_id=cid,
                elapsed_ms=elapsed,
            )

    def execute_stream(
        self,
        action: str,
        resource_command: Optional[str] = None,
        resource_description: str = "",
        user_id: str = "pihu_user",
        tool_fn: Any = None,
        tool_args: tuple = None,
        tool_kwargs: dict = None,
        chain_depth: int = 0,
    ) -> Generator[str, None, None]:
        """
        Execute a streaming tool invocation through the policy pipeline.
        Yields chunks from the tool function if approved.
        """
        # Use non-streaming execute for policy check
        result = self.execute(
            action=action,
            resource_command=resource_command,
            resource_description=resource_description,
            user_id=user_id,
            tool_fn=None,  # Don't execute yet
            chain_depth=chain_depth,
        )
        
        if result.denied:
            yield f"🚫 Action denied: {result.denial_reason}"
            return
        
        if result.dry_run:
            yield str(result.output)
            return
        
        # Execute the streaming tool
        if tool_fn:
            try:
                args = tool_args or ()
                kwargs = tool_kwargs or {}
                
                if self.session_trust:
                    self.session_trust.touch()
                
                for chunk in tool_fn(*args, **kwargs):
                    yield chunk
                    
            except Exception as e:
                log.error("💥 Streaming tool execution failed: %s", e)
                yield f"Execution failed: {str(e)[:100]}"

    def _request_approval(self, decision) -> bool:
        """Request user approval for a policy decision."""
        if self._approval_callback:
            try:
                prompt = decision.prompt_message or f"Allow action? Reason: {decision.reason}"
                return self._approval_callback(prompt)
            except Exception as e:
                log.error("Approval callback failed: %s", e)
                return False
        
        # No callback = auto-deny for safety
        log.warning("No approval callback — auto-denying approval request")
        return False

    def _record_audit(self, event: str, action: str, decision, 
                      success: bool = True, error: str = ""):
        """Record tool invocation in the audit log."""
        if not self.audit:
            return
        
        try:
            from security.security_core import ThreatLevel
            
            risk_map = {
                0.0: ThreatLevel.SAFE,
                0.3: ThreatLevel.LOW,
                0.5: ThreatLevel.MEDIUM,
                0.7: ThreatLevel.HIGH,
                0.9: ThreatLevel.CRITICAL,
            }
            
            # Find closest threat level
            threat = ThreatLevel.SAFE
            for threshold, level in sorted(risk_map.items()):
                if decision.risk_score >= threshold:
                    threat = level
            
            self.audit.record(
                action=event,
                command=f"{action}:{decision.reason[:100]}",
                threat_level=threat,
                result="OK" if success else f"FAIL:{error[:50]}",
                metadata={
                    "correlation_id": decision.correlation_id,
                    "matched_rules": decision.matched_rules,
                    "risk_score": decision.risk_score,
                },
            )
        except Exception as e:
            log.error("Audit recording failed: %s", e)

    def get_stats(self) -> dict:
        """Return broker statistics."""
        return {
            "total_requests": self._total_requests,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
            "total_approvals_requested": self._total_approvals,
            "policy_attached": self.policy_engine is not None,
            "audit_attached": self.audit is not None,
        }

    def set_approval_callback(self, callback):
        """Set or replace the approval callback function."""
        self._approval_callback = callback
        log.info("🔧 Approval callback updated")
