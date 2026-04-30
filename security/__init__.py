"""
Pihu — Security Package
Deterministic security stack for the Pihu autonomous agent.

Components:
  PolicyEngine      — evaluates every tool request against versioned rules
  ToolBroker        — the only component allowed to invoke tools
  FilesystemGuard   — path normalization, workspace boundaries, protected paths
  CommandClassifier  — shell command tokenization and risk scoring
  NetworkGuard      — default-deny egress, domain allowlists
  SessionTrustManager — trust levels with escalation and timeout
  ContentTrustManager — content origin labeling for prompt injection defense
  SecretRedactor    — secret pattern scrubbing for logs and output
  
  SecurityManager   — legacy unified API (Vault, AuditLog, Sentinel, Integrity)
"""
