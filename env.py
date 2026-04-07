"""
Sentinel-Log-Shield v2: Interactive Security Investigation Environment.

A genuine multi-step RL environment where an agent investigates a simulated
data breach through a procedurally-generated entity graph. Actions include
scanning visible logs, investigating entities to reveal hidden connections,
redacting discovered PII, and submitting findings.

Key RL properties:
- State transitions: investigating entity X reveals connected logs/entities
- Sequential decisions: each discovery opens new investigation paths
- Strategy required: limited step budget forces prioritization
- Hidden information: deep secrets only found through multi-step investigation
- Procedural generation: every episode is unique
"""

import re
import random
import hashlib
import string
from typing import Dict, List, Set, Tuple, Optional, Any
from models import (
    ActionType, AgentAction, Difficulty, Observation, Reward,
    StepResult, ResetResult, EnvironmentState,
)


# ============================================================================
# PROCEDURAL SCENARIO GENERATION
# ============================================================================

# Name pools
FIRST_NAMES = [
    "alice", "bob", "charlie", "diana", "evan", "frank", "grace", "henry",
    "irene", "jack", "kate", "leo", "mia", "noah", "olivia", "paul",
    "quinn", "rachel", "sam", "tara", "uma", "victor", "wendy", "xander",
    "yara", "zach", "amit", "bhavesh", "chen", "deepa", "elena", "farid",
]

DOMAINS = [
    "corp.com", "internal.io", "devops.net", "staging.dev", "prod.cloud",
    "acme-corp.com", "techstart.io", "finserv.net", "healthdata.org",
]

SERVICES = [
    "auth-service", "api-gateway", "user-mgmt", "secrets-vault",
    "payment-service", "data-pipeline", "config-server", "ci-runner",
    "log-aggregator", "identity-provider", "cache-redis", "db-postgres",
]

TABLES = [
    "users", "transactions", "sessions", "audit_log", "credentials",
    "api_keys", "permissions", "deployments", "secrets", "config",
]

# Token patterns for procedural generation
TOKEN_PREFIXES = {
    "stripe": "sk_live_",
    "aws_access": "AKIA",
    "github": "ghp_",
    "huggingface": "hf_",
    "jwt": "eyJhbGciOi",
    "generic_api": "api_key_",
    "bearer": "Bearer ",
}


def _random_ip() -> str:
    """Generate a realistic-looking internal/external IP."""
    prefixes = [
        (10, random.randint(0, 255), random.randint(0, 255)),
        (172, random.randint(16, 31), random.randint(0, 255)),
        (192, 168, random.randint(0, 255)),
        (203, 0, 113),  # TEST-NET-3
    ]
    prefix = random.choice(prefixes)
    return f"{prefix[0]}.{prefix[1]}.{prefix[2]}.{random.randint(1, 254)}"


def _random_token(token_type: str) -> str:
    """Generate a realistic-looking secret token."""
    prefix = TOKEN_PREFIXES.get(token_type, "tok_")
    charset = string.ascii_letters + string.digits
    if token_type == "aws_access":
        # AWS access keys are 20 uppercase alphanumeric chars
        return prefix + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
    elif token_type == "stripe":
        return prefix + "".join(random.choices(charset, k=24))
    elif token_type in ("github", "huggingface"):
        return prefix + "".join(random.choices(charset, k=30))
    elif token_type == "jwt":
        return prefix + "".join(random.choices(charset, k=40))
    else:
        return prefix + "".join(random.choices(charset, k=20))


def _random_timestamp() -> str:
    """Generate a realistic timestamp."""
    h = random.randint(0, 23)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return f"2026-04-07 {h:02d}:{m:02d}:{s:02d}"


# ============================================================================
# LOG TEMPLATES (50+ templates for procedural generation)
# ============================================================================

# Each template returns (log_string, set_of_pii_in_this_log)
# Templates are organized by what PII they reveal

def _make_log_templates():
    """Returns a dict of template functions keyed by PII types they reveal."""
    templates = {
        # Surface-level templates (Layer 0 — visible on reset)
        "surface": [
            lambda u, e, ip, ts: (
                f"{ts} AUTH: Failed login for {e} from {ip} (attempt 3/5)",
                {"email": {e}, "ip": {ip}},
            ),
            lambda u, e, ip, ts: (
                f"{ts} ALERT: Suspicious activity detected from {ip}, user={u}",
                {"ip": {ip}, "username": {u}},
            ),
            lambda u, e, ip, ts: (
                f"{ts} AUTH: User '{u}' logged in from {ip} at {ts.split(' ')[1]}",
                {"username": {u}, "ip": {ip}},
            ),
            lambda u, e, ip, ts: (
                f"{ts} MONITOR: Email notification sent to {e} regarding account lock",
                {"email": {e}},
            ),
            lambda u, e, ip, ts: (
                f"{ts} FIREWALL: Connection from {ip} to port 443 accepted",
                {"ip": {ip}},
            ),
            lambda u, e, ip, ts: (
                f"{ts} AUDIT: User '{u}' ({e}) performed password reset from {ip}",
                {"username": {u}, "email": {e}, "ip": {ip}},
            ),
        ],
        # Investigation-revealed templates (Layer 1+)
        "user_linked": [
            lambda u, e, ip, ts, svc: (
                f"{ts} DEBUG [{svc}]: User '{u}' accessed endpoint /api/v2/secrets",
                {"username": {u}},
            ),
            lambda u, e, ip, ts, svc: (
                f"{ts} ACCESS: {e} granted role 'admin' on {svc} from {ip}",
                {"email": {e}, "ip": {ip}},
            ),
            lambda u, e, ip, ts, svc: (
                f"{ts} DB: User '{u}' queried {random.choice(TABLES)} (rows: {random.randint(1, 500)})",
                {"username": {u}},
            ),
            lambda u, e, ip, ts, svc: (
                f"{ts} SESSION: New session for '{u}' from {ip} (browser: Chrome/120)",
                {"username": {u}, "ip": {ip}},
            ),
        ],
        # Secret-revealing templates (deep layers)
        "token_linked": [
            lambda u, tok, ts, svc, tok_type: (
                f"{ts} DEBUG [{svc}]: Token {tok} used for API authentication",
                {"token": {tok}},
            ),
            lambda u, tok, ts, svc, tok_type: (
                f"{ts} CONFIG: Loaded {tok_type}_key={tok} for {svc}",
                {"token": {tok}},
            ),
            lambda u, tok, ts, svc, tok_type: (
                f"{ts} ERROR: Auth failed with credential {tok} in {svc} module (line {random.randint(20, 200)})",
                {"token": {tok}},
            ),
            lambda u, tok, ts, svc, tok_type: (
                f"{ts} TRACE: Stack dump includes secret {tok} at {svc}:L{random.randint(10, 300)}",
                {"token": {tok}},
            ),
        ],
        # IP-linked templates (revealed when investigating an IP)
        "ip_linked": [
            lambda u, e, ip, ts, svc: (
                f"{ts} NETWORK: {ip} established {random.randint(1, 50)} connections to {svc}",
                {"ip": {ip}},
            ),
            lambda u, e, ip, ts, svc: (
                f"{ts} PROXY: Request from {ip} forwarded to {svc} (user-agent: python-requests/2.31)",
                {"ip": {ip}},
            ),
        ],
    }
    return templates


# ============================================================================
# SCENARIO GENERATOR
# ============================================================================

class Scenario:
    """A procedurally-generated investigation scenario."""

    def __init__(self, difficulty: Difficulty, seed: Optional[int] = None):
        self.difficulty = difficulty
        self.seed = seed if seed is not None else random.randint(0, 2**31)
        self.rng = random.Random(self.seed)

        # Difficulty parameters
        cfg = {
            Difficulty.EASY:   {"n_users": 2, "n_layers": 2, "budget": 12, "n_secrets": 1},
            Difficulty.MEDIUM: {"n_users": 3, "n_layers": 3, "budget": 10, "n_secrets": 2},
            Difficulty.HARD:   {"n_users": 4, "n_layers": 4, "budget": 8,  "n_secrets": 3},
        }[difficulty]

        self.budget = cfg["budget"]
        self.n_layers = cfg["n_layers"]

        # Generate entities
        names = self.rng.sample(FIRST_NAMES, cfg["n_users"])
        self.users = {
            name: {
                "email": f"{name}.{self.rng.choice(['dev','ops','sec'])}@{self.rng.choice(DOMAINS)}",
                "ips": [_random_ip() for _ in range(self.rng.randint(1, 2))],
                "services": self.rng.sample(SERVICES, self.rng.randint(1, 3)),
            }
            for name in names
        }

        # Generate secrets (linked to users or services)
        self.secrets = {}
        token_types = self.rng.sample(list(TOKEN_PREFIXES.keys()), min(cfg["n_secrets"], len(TOKEN_PREFIXES)))
        for i, tok_type in enumerate(token_types):
            owner = self.rng.choice(names)
            self.secrets[f"secret_{i}"] = {
                "token": _random_token(tok_type),
                "type": tok_type,
                "owner": owner,
                "service": self.rng.choice(self.users[owner]["services"]),
            }

        # Build investigation graph: entity → set of connected entities
        self.entity_graph: Dict[str, Set[str]] = {}
        for name, info in self.users.items():
            # Username connects to email, IPs
            self.entity_graph[name] = {info["email"]} | set(info["ips"])
            # Email connects to username, IPs
            self.entity_graph[info["email"]] = {name} | set(info["ips"])
            # IPs connect to username, email
            for ip in info["ips"]:
                if ip not in self.entity_graph:
                    self.entity_graph[ip] = set()
                self.entity_graph[ip].add(name)
                self.entity_graph[ip].add(info["email"])

        # Secrets are linked to their owner (investigating owner reveals secrets)
        for sid, sinfo in self.secrets.items():
            owner = sinfo["owner"]
            self.entity_graph.setdefault(owner, set()).add(sinfo["token"])
            # Investigating an IP of the owner may also reveal the secret
            for ip in self.users[owner]["ips"]:
                self.entity_graph.setdefault(ip, set()).add(sinfo["token"])

        # Generate logs per layer
        self.layers: List[List[Tuple[str, Dict[str, Set[str]]]]] = []
        templates = _make_log_templates()
        self._generate_layers(templates)

        # All PII in the scenario (ground truth)
        self.all_pii: Dict[str, Set[str]] = {
            "email": set(), "ip": set(), "username": set(), "token": set(),
        }
        for name, info in self.users.items():
            self.all_pii["username"].add(name)
            self.all_pii["email"].add(info["email"])
            for ip in info["ips"]:
                self.all_pii["ip"].add(ip)
        for sid, sinfo in self.secrets.items():
            self.all_pii["token"].add(sinfo["token"])

        # Flat set of all PII values
        self.all_pii_flat: Set[str] = set()
        for pii_set in self.all_pii.values():
            self.all_pii_flat |= pii_set

        # Track which PII is in which layer
        self.pii_by_layer: List[Set[str]] = []
        for layer in self.layers:
            layer_pii = set()
            for _, pii_dict in layer:
                for pii_set in pii_dict.values():
                    layer_pii |= pii_set
            self.pii_by_layer.append(layer_pii)

    def _generate_layers(self, templates):
        """Generate log entries for each investigation layer."""
        # Layer 0: Surface logs (visible on reset)
        layer0 = []
        surface_tmpls = templates["surface"]
        for name in list(self.users.keys())[:2]:  # Show first 2 users in surface
            info = self.users[name]
            ts = _random_timestamp()
            tmpl = self.rng.choice(surface_tmpls)
            log, pii = tmpl(name, info["email"], self.rng.choice(info["ips"]), ts)
            layer0.append((log, pii))
        # Add 1-2 more surface logs
        for _ in range(self.rng.randint(1, 2)):
            name = self.rng.choice(list(self.users.keys()))
            info = self.users[name]
            ts = _random_timestamp()
            tmpl = self.rng.choice(surface_tmpls)
            log, pii = tmpl(name, info["email"], self.rng.choice(info["ips"]), ts)
            layer0.append((log, pii))
        self.layers.append(layer0)

        # Deeper layers: revealed by investigation
        user_linked = templates["user_linked"]
        ip_linked = templates["ip_linked"]
        token_linked = templates["token_linked"]

        for layer_idx in range(1, self.n_layers):
            layer = []
            for name, info in self.users.items():
                ts = _random_timestamp()
                svc = self.rng.choice(info["services"])

                # User-linked logs
                if self.rng.random() < 0.7:
                    tmpl = self.rng.choice(user_linked)
                    log, pii = tmpl(name, info["email"], self.rng.choice(info["ips"]), ts, svc)
                    layer.append((log, pii))

                # IP-linked logs
                if self.rng.random() < 0.5:
                    tmpl = self.rng.choice(ip_linked)
                    log, pii = tmpl(name, info["email"], self.rng.choice(info["ips"]), ts, svc)
                    layer.append((log, pii))

            # Token-linked logs appear in deeper layers
            if layer_idx >= self.n_layers - 2:
                for sid, sinfo in self.secrets.items():
                    ts = _random_timestamp()
                    tmpl = self.rng.choice(token_linked)
                    log, pii = tmpl(
                        sinfo["owner"], sinfo["token"], ts,
                        sinfo["service"], sinfo["type"],
                    )
                    layer.append((log, pii))

            self.layers.append(layer)

    def get_entity_layer(self, entity: str) -> int:
        """Return which layer an entity's logs first appear in."""
        for i, layer in enumerate(self.layers):
            for _, pii_dict in layer:
                for pii_set in pii_dict.values():
                    if entity in pii_set:
                        return i
        return self.n_layers - 1


# ============================================================================
# ENVIRONMENT
# ============================================================================

class SentinelEnvironment:
    """
    Interactive Security Investigation RL Environment.

    The agent investigates a simulated data breach through multi-step
    exploration of an entity graph. Actions include scanning visible logs,
    investigating entities to reveal hidden connections, redacting discovered
    PII, and submitting findings.

    Implements Gymnasium-style API: reset(), step(), state()
    """

    def __init__(self):
        self.scenario: Optional[Scenario] = None
        self.is_running = False

        # Episode state
        self.steps_used = 0
        self.total_reward = 0.0
        self.action_history: List[Dict[str, Any]] = []

        # Investigation state
        self.visible_log_indices: Set[int] = set()  # Which logs are visible
        self.all_logs: List[Tuple[str, Dict[str, Set[str]]]] = []  # All logs flat
        self.discovered_entities: Set[str] = set()  # Entities found so far
        self.investigated_entities: Set[str] = set()  # Entities already investigated
        self.redacted_pii: Set[str] = set()  # PII already redacted
        self.scan_performed: bool = False

    def reset(self, difficulty: str = "medium", seed: Optional[int] = None) -> ResetResult:
        """Reset environment and generate a new investigation scenario."""
        diff = Difficulty(difficulty) if isinstance(difficulty, str) else difficulty
        self.scenario = Scenario(difficulty=diff, seed=seed)
        self.is_running = True
        self.steps_used = 0
        self.total_reward = 0.0
        self.action_history = []
        self.discovered_entities = set()
        self.investigated_entities = set()
        self.redacted_pii = set()
        self.scan_performed = False

        # Flatten all logs and set layer 0 as visible
        self.all_logs = []
        self.visible_log_indices = set()
        offset = 0
        for layer_idx, layer in enumerate(self.scenario.layers):
            for i, entry in enumerate(layer):
                self.all_logs.append(entry)
                if layer_idx == 0:
                    self.visible_log_indices.add(offset + i)
            offset += len(layer)

        obs = self._build_observation(
            hint=f"You're investigating a potential data breach. {len(self.scenario.all_pii_flat)} PII items are hidden across {self.scenario.n_layers} layers. Start by scanning the visible logs."
        )

        return ResetResult(
            observation=obs,
            info={
                "scenario_seed": self.scenario.seed,
                "difficulty": difficulty,
                "total_pii": len(self.scenario.all_pii_flat),
                "n_layers": self.scenario.n_layers,
                "budget": self.scenario.budget,
            },
        )

    def step(self, action: AgentAction) -> StepResult:
        """Process agent action and return step result."""
        if not self.is_running:
            raise ValueError("Episode not running. Call reset() first.")

        self.steps_used += 1
        reward = Reward(total_reward=0.0)
        hint = ""
        terminated = False
        truncated = False

        if action.action_type == ActionType.SCAN:
            reward, hint = self._handle_scan()
        elif action.action_type == ActionType.INVESTIGATE:
            reward, hint = self._handle_investigate(action.target_entity)
        elif action.action_type == ActionType.REDACT:
            reward, hint = self._handle_redact(action.redactions or [])
        elif action.action_type == ActionType.SUBMIT:
            reward, hint = self._handle_submit()
            terminated = True
        else:
            reward = Reward(
                total_reward=-0.1,
                penalty=-0.1,
                feedback="Invalid action type.",
            )

        self.total_reward += reward.total_reward

        # Check truncation (out of budget)
        if self.steps_used >= self.scenario.budget and not terminated:
            truncated = True
            # Auto-submit on truncation
            submit_reward, _ = self._handle_submit()
            reward = submit_reward
            self.total_reward += reward.total_reward
            hint = "⏰ Investigation budget exhausted. Auto-submitting findings."

        if terminated or truncated:
            self.is_running = False

        # Record action
        self.action_history.append({
            "step": self.steps_used,
            "action": action.action_type.value,
            "target": action.target_entity,
            "reward": reward.total_reward,
            "terminated": terminated,
            "truncated": truncated,
        })

        obs = self._build_observation(hint=hint)

        return StepResult(
            observation=obs,
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            info={
                "step": self.steps_used,
                "cumulative_reward": self.total_reward,
                "pii_found": len(self.redacted_pii),
                "pii_total": len(self.scenario.all_pii_flat),
            },
        )

    def state(self) -> EnvironmentState:
        """Return current environment state."""
        obs = self._build_observation(hint="")
        return EnvironmentState(
            current_observation=obs,
            episode_step=self.steps_used,
            total_reward=self.total_reward,
            action_history=self.action_history,
            is_running=self.is_running,
            difficulty=self.scenario.difficulty.value if self.scenario else "medium",
            scenario_seed=self.scenario.seed if self.scenario else None,
        )

    # ──────────────────── Action Handlers ────────────────────

    def _handle_scan(self) -> Tuple[Reward, str]:
        """Scan visible logs to extract PII entities."""
        if self.scan_performed:
            # Repeated scan — still useful if new logs revealed
            pass

        self.scan_performed = True
        newly_discovered = set()

        # Extract PII from visible logs
        for idx in self.visible_log_indices:
            log_text, pii_dict = self.all_logs[idx]
            for pii_type, pii_set in pii_dict.items():
                for item in pii_set:
                    if item not in self.discovered_entities:
                        newly_discovered.add(item)
                        self.discovered_entities.add(item)

        n_new = len(newly_discovered)
        reward_val = 0.1 * n_new  # Small reward for discovery

        hint = ""
        if n_new > 0:
            investigatable = [e for e in self.discovered_entities if e not in self.investigated_entities]
            hint = f"Scan found {n_new} new entities. "
            if investigatable:
                hint += f"Try investigating: {investigatable[0]}"
        else:
            hint = "No new entities found in visible logs. Try investigating known entities."

        return Reward(
            redaction_score=0.0,
            discovery_bonus=reward_val,
            total_reward=reward_val,
            feedback=f"Scan complete. {n_new} new entities discovered.",
            metrics={"new_entities": n_new, "total_discovered": len(self.discovered_entities)},
        ), hint

    def _handle_investigate(self, target: Optional[str]) -> Tuple[Reward, str]:
        """Investigate an entity to reveal connected logs."""
        if not target:
            return Reward(
                total_reward=-0.1,
                penalty=-0.1,
                feedback="INVESTIGATE requires a target_entity.",
            ), "Please provide a target_entity to investigate."

        if target in self.investigated_entities:
            return Reward(
                total_reward=-0.05,
                penalty=-0.05,
                feedback=f"Already investigated '{target}'. Try a different entity.",
            ), f"'{target}' was already investigated. Choose another entity."

        self.investigated_entities.add(target)

        # Find connected entities and reveal their logs
        connected = self.scenario.entity_graph.get(target, set())
        newly_visible = 0
        newly_discovered = set()

        # Reveal logs that contain the target or connected entities
        search_entities = {target} | connected
        for idx, (log_text, pii_dict) in enumerate(self.all_logs):
            if idx in self.visible_log_indices:
                continue
            # Check if this log mentions any search entity
            all_pii_in_log = set()
            for pii_set in pii_dict.values():
                all_pii_in_log |= pii_set
            if search_entities & all_pii_in_log:
                self.visible_log_indices.add(idx)
                newly_visible += 1
                # Also discover entities in newly visible logs
                for pii_type, pii_set in pii_dict.items():
                    for item in pii_set:
                        if item not in self.discovered_entities:
                            newly_discovered.add(item)
                            self.discovered_entities.add(item)

        # Discovery bonus — deeper entities get higher bonus
        discovery_bonus = 0.15 * len(newly_discovered)
        # Bonus for revealing token-type entities (secrets)
        secret_tokens = self.scenario.all_pii.get("token", set())
        secret_found = newly_discovered & secret_tokens
        if secret_found:
            discovery_bonus += 0.3 * len(secret_found)

        hint = f"Investigation of '{target}' revealed {newly_visible} new logs and {len(newly_discovered)} entities."
        if secret_found:
            hint += " 🔑 CRITICAL: Secret tokens discovered!"

        investigatable = [e for e in self.discovered_entities
                         if e not in self.investigated_entities
                         and e not in self.redacted_pii]
        if investigatable:
            hint += f" Next target suggestion: {investigatable[0]}"

        return Reward(
            discovery_bonus=discovery_bonus,
            total_reward=discovery_bonus,
            feedback=f"Investigated '{target}'. Found {len(newly_discovered)} new entities, {newly_visible} new logs.",
            metrics={
                "new_logs_revealed": newly_visible,
                "new_entities": len(newly_discovered),
                "secrets_found": len(secret_found),
            },
        ), hint

    def _handle_redact(self, redactions: List[Dict[str, str]]) -> Tuple[Reward, str]:
        """Submit PII items for redaction and scoring."""
        if not redactions:
            return Reward(
                total_reward=-0.05,
                penalty=-0.05,
                feedback="No redactions provided.",
            ), "Please provide redactions: [{'original': '...', 'type': 'email|ip|username|token'}]"

        correct = 0
        false_positives = 0
        already_redacted = 0
        newly_redacted = []

        ground_truth = self.scenario.all_pii_flat

        for item in redactions:
            original = item.get("original", "")
            if original in self.redacted_pii:
                already_redacted += 1
                continue
            if original in ground_truth:
                correct += 1
                self.redacted_pii.add(original)
                newly_redacted.append(original)
            else:
                false_positives += 1

        # Compute per-step reward
        total_pii = len(ground_truth)
        redaction_score = (correct / total_pii) if total_pii > 0 else 0.0
        penalty = -0.15 * false_positives

        # Check if secrets were redacted (bonus)
        secret_tokens = self.scenario.all_pii.get("token", set())
        secrets_redacted = set(newly_redacted) & secret_tokens
        secret_bonus = 0.2 * len(secrets_redacted)

        total_reward = redaction_score + penalty + secret_bonus

        # Coverage so far
        coverage = len(self.redacted_pii) / total_pii if total_pii > 0 else 0.0

        hint = f"Redacted {correct} items correctly."
        if false_positives:
            hint += f" ⚠️ {false_positives} false positives (penalty applied)."
        hint += f" Coverage: {len(self.redacted_pii)}/{total_pii} ({coverage:.0%})"

        remaining = ground_truth - self.redacted_pii
        if not remaining:
            hint += " 🎉 All PII found! Consider submitting."

        return Reward(
            redaction_score=redaction_score,
            penalty=penalty,
            discovery_bonus=secret_bonus,
            total_reward=total_reward,
            feedback=f"{correct} correct, {false_positives} false positives, {already_redacted} duplicates.",
            metrics={
                "correct": correct,
                "false_positives": false_positives,
                "coverage": coverage,
                "items_redacted_total": len(self.redacted_pii),
                "items_remaining": len(remaining),
            },
        ), hint

    def _handle_submit(self) -> Tuple[Reward, str]:
        """Submit findings and compute final score."""
        ground_truth = self.scenario.all_pii_flat
        total_pii = len(ground_truth)

        # Precision / Recall / F1
        true_positives = len(self.redacted_pii & ground_truth)
        false_positives = len(self.redacted_pii - ground_truth)
        false_negatives = len(ground_truth - self.redacted_pii)

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / total_pii if total_pii > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # Discovery rate: what fraction of PII was even discovered (seen in scan/investigate)
        discovered_pii = self.discovered_entities & ground_truth
        discovery_rate = len(discovered_pii) / total_pii if total_pii > 0 else 0.0

        # Efficiency bonus: steps saved
        budget = self.scenario.budget
        steps_saved = max(0, budget - self.steps_used)
        efficiency_bonus = 0.05 * steps_saved

        # Secret penalty: critical secrets missed
        secret_tokens = self.scenario.all_pii.get("token", set())
        missed_secrets = secret_tokens - self.redacted_pii
        secret_penalty = -0.3 * len(missed_secrets)

        # Final score composition
        base_score = f1 * 0.7  # F1 is 70% of score
        discovery_component = discovery_rate * 0.2  # Discovery is 20%
        completeness = recall * 0.1  # Raw recall is 10%

        total_reward = base_score + discovery_component + completeness + efficiency_bonus + secret_penalty

        hint = f"📊 Final Score: {total_reward:.3f} | F1: {f1:.3f} | Discovery: {discovery_rate:.0%} | "
        hint += f"Redacted: {true_positives}/{total_pii}"
        if missed_secrets:
            hint += f" | ⚠️ CRITICAL: {len(missed_secrets)} secret(s) missed!"

        return Reward(
            redaction_score=base_score + completeness,
            discovery_bonus=discovery_component,
            efficiency_bonus=efficiency_bonus,
            penalty=secret_penalty,
            total_reward=total_reward,
            feedback=hint,
            metrics={
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "discovery_rate": discovery_rate,
                "efficiency_bonus": efficiency_bonus,
                "missed_secrets": len(missed_secrets),
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "steps_used": self.steps_used,
                "steps_budget": budget,
                "total_score": max(0.0, min(1.0, total_reward)),
                "total_pii": total_pii,
                "grade": self._letter_grade(max(0.0, min(1.0, total_reward))),
            },
        ), hint

    # ──────────────────── Helpers ────────────────────

    @staticmethod
    def _letter_grade(score: float) -> str:
        """Assign a letter grade based on total score."""
        if score >= 0.95: return "S"
        if score >= 0.85: return "A"
        if score >= 0.70: return "B"
        if score >= 0.50: return "C"
        if score >= 0.30: return "D"
        return "F"

    def _build_observation(self, hint: str = "") -> Observation:
        """Construct the current observation for the agent."""
        visible_logs = [self.all_logs[i][0] for i in sorted(self.visible_log_indices)]

        # Investigation targets: discovered but not yet investigated
        targets = sorted(
            e for e in self.discovered_entities
            if e not in self.investigated_entities
        )

        # Scan results: most recent scan findings
        scan_results = [
            {"original": e, "type": self._classify_entity(e)}
            for e in sorted(self.discovered_entities)
        ]

        redacted_items = [
            {"original": e, "type": self._classify_entity(e)}
            for e in sorted(self.redacted_pii)
        ]

        total_pii = len(self.scenario.all_pii_flat) if self.scenario else 0

        return Observation(
            visible_logs=visible_logs,
            discovered_entities=sorted(self.discovered_entities),
            investigation_targets=targets,
            scan_results=scan_results,
            redacted_items=redacted_items,
            steps_remaining=max(0, self.scenario.budget - self.steps_used) if self.scenario else 0,
            steps_used=self.steps_used,
            difficulty=self.scenario.difficulty.value if self.scenario else "medium",
            hint=hint,
            score_so_far=self.total_reward,
            total_pii_to_find=total_pii,
            pii_found_count=len(self.redacted_pii),
        )

    def _classify_entity(self, entity: str) -> str:
        """Classify a PII entity into its type."""
        if "@" in entity and "." in entity:
            return "email"
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", entity):
            return "ip"
        if entity in (self.scenario.all_pii.get("token", set()) if self.scenario else set()):
            return "token"
        return "username"
