"""Durable inference recovery, separate from economic actions and billing.

Only an explicitly frozen operating runner supplies perform(), ledger checks,
source verification and approved prefix references. No transport or allocation
on import. Archived runs are read-only; a continuation has its own lineage.
"""

from copy import deepcopy
from decimal import Decimal
import fcntl
import hashlib
import json
from pathlib import Path
import time

from paper3 import retrospective_deepinfra_recovery_evidence_v2 as prior
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_billing_separation as billing
from paper3.pivot_b_budget import atomic, identifier

VERSION = "paper3-graceful-inference-recovery-v1"
COOLDOWNS = (300, 600, 1200)


class Paused(BaseException):
    """Operational pause must not become an economic failure or terminal run."""

    def __init__(self, reason, *, automatic=False):
        super().__init__(reason)
        self.reason, self.automatic = reason, automatic


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    from paper3.retrospective_episode_journal import load as checked

    return checked(path)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def overload(row):
    """Known pre-answer overload may have an opaque ID and absent receipts.

    IDs and all receipts remain unmodified. Uncertain charges must retain their
    entire reservation before another request. No answers/usage/content failures,
    unknown receipt errors, auth/key limits or provider fallback are retried.
    """
    result = dict(
        eligible=False,
        reason="not_verified_overload",
        delay=None,
        full_failed_reservation_retained=True,
    )
    try:
        s, request = row["stream"], row["request"]
        http = s["http_status"]
        transient_http = type(http) is int and http in (429, 500, 502, 503, 504)
        transient_connection = http is None and s["error_type"] in (
            "TimeoutError",
            "URLError",
            "ConnectionResetError",
            "RemoteDisconnected",
        )
        if not (
            row["status"] == "recorded"
            and not row.get("instrument_error")
            and (
                transient_http
                and s["error_type"] == "HTTPError"
                or transient_connection
            )
            and s["lines"] == []
            and type(s["line_count"]) is int
            and s["line_count"] == 0
            and type(s["byte_count"]) is int
            and s["byte_count"] == 0
            and s.get("first_line_unix") is None
            and s.get("last_line_unix") is None
            and s.get("secret_redacted") is False
            and s.get("error_body_redacted", False) is False
            and s["http_error_body_truncated"] is False
        ):
            return result
        expected = route.request(dict(tool_choice="auto", tools=[{}]), 0)
        if not (
            request["model"] == route.MODEL
            and request["provider"] == expected["provider"]
            and request["reasoning"] == expected["reasoning"]
            and request["stream"] is True
        ):
            return result
        body = {}
        if s.get("http_error_body"):
            try:
                body = json.loads(
                    s["http_error_body"],
                    object_pairs_hook=prior.unique_object,
                    parse_constant=prior.reject_constant,
                )
            except (ValueError, TypeError):
                # A gateway may return an HTML 502/504, never an agent action.
                if http not in (500, 502, 503, 504):
                    return result
        if type(body) is not dict:
            return result
        e, types = body.get("error", {}), []
        if type(e) is not dict:
            return result
        m = e.get("metadata", {})
        if type(m) is not dict:
            return result
        if http == 429 and not (
            type(e.get("code")) is int
            and e["code"] == 429
            and m.get("provider_name") == route.PROVIDER
            and m.get("limit_source") == "upstream_provider_shared_pool"
            and m.get("is_byok") is False
        ):
            return result
        if e.get("code") is not None and e["code"] != http:
            return result
        for value in (body, e, m):
            typed = value.get("error_type")
            if typed is not None:
                if typed not in prior.TRANSIENT_TYPES:
                    return result
                types.append(typed)
            # Usage or a generated answer is not merely an opaque request ID.
            if (
                value.get("usage") is not None
                or value.get("choices")
                or value.get("output")
            ):
                return result
        receipts = row["receipts"]
        if receipts and not (
            len(receipts) == 4
            and [v.get("scheduled_offset_seconds") for v in receipts] == billing.OFFSETS
            and all(billing.absent_observation(v) for v in receipts)
        ):
            return result
        reserve = Decimal(row["reserved_usd"])
        assessment = row["assessment"]
        if not (
            reserve.is_finite()
            and reserve > 0
            and Decimal(assessment["accounted_usd"]) == reserve
            and assessment["receipt_certified"] is False
            and assessment["stream"]["usage"] is None
            and not assessment["stream"]["complete"]
            and not assessment["stream"]["finish_reasons"]
        ):
            return result
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return result
    return dict(
        result,
        eligible=True,
        reason="known_overload_no_answer_cost_retained",
        delay=prior.retry_after_seconds(s),
    )


class DurableResponses:
    """One writer; replay accepted evidence instead of resending its request.

    perform(request, logical_id, physical_id) makes AT MOST ONE POST, durably
    reserves before sending, settles/preserves cost and returns its record path.
    check_record(path, row) verifies physical identity, ledger and settlement.
    A crash between sending and durable evidence pauses for review, never blindly
    sends again. A crash after evidence but before cache commit adopts that same
    evidence. These guarantees require the separately tested operating adapter.
    """

    def __init__(
        self,
        root,
        repo,
        *,
        protocol,
        classify,
        perform,
        check_record,
        verify,
        prefix=None,
        initial_failures=None,
        maximum_physical=448,
        maximum_reissues=40,
        recover_claim=None,
        clock=time.time,
        sleep=time.sleep,
    ):
        self.root, self.repo = Path(root), Path(repo).resolve(strict=True)
        self.protocol = protocol
        self.classify, self.perform, self.check_record = classify, perform, check_record
        self.verify, self.clock, self.sleep = verify, clock, sleep
        self.prefix = deepcopy(prefix or {})
        self.initial_failures = deepcopy(initial_failures or {})
        self.maximum_physical = maximum_physical
        self.maximum_reissues, self.recover_claim = maximum_reissues, recover_claim
        require(
            type(maximum_physical) is int and 0 < maximum_physical <= 560,
            "physical ceiling",
        )
        require(
            type(maximum_reissues) is int and 0 <= maximum_reissues <= 80,
            "reissue ceiling",
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / "writer.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for name in ("accepted", "attempts"):
                (self.root / name).mkdir(exist_ok=True)
            require(not list(self.root.rglob("*.partial")), "interrupted partial write")
            self.verify()
        except BaseException:
            self.lock.close()
            raise

    def close(self):
        self.lock.close()

    def reference(self, path):
        original = Path(path)
        path = original.resolve(strict=True)
        require(
            path.is_relative_to(self.repo) and not original.is_symlink(),
            "evidence must be in the same repository",
        )
        return dict(path=path.relative_to(self.repo).as_posix(), sha256=digest(path))

    def read(self, ref):
        require(set(ref) == {"path", "sha256"}, "exact evidence reference")
        path = self.repo / ref["path"]
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(self.repo)
            and digest(path) == ref["sha256"],
            "immutable response reference changed",
        )
        row = load(path)
        self.check_record(path, row)
        return row

    def _score(self, row, request, key):
        bound = route.reservation(request)
        require(
            row["request_text"] == bound["request_text"]
            and row["request_sha256"]
            == hashlib.sha256(bound["request_text"].encode()).hexdigest(),
            "replayed wire/request differs",
        )
        return self.classify(row, request, key)

    def _accepted(self, ref, request, key):
        row = self.read(ref)
        score = self._score(row, request, key)
        require(
            score["status"] in ("recorded_valid", "content_failed", "resource_failed"),
            "cached action no longer validates",
        )
        # The physical ID and original protocol remain in the immutable raw row.
        # The existing economic executor consumes the assigned logical identity.
        return dict(deepcopy(row), id=key)

    def respond(self, request, key):
        try:
            return self._respond(request, key)
        except Exception as exc:
            raise Paused("integrity_or_adapter:" + type(exc).__name__) from exc

    def _respond(self, request, key):
        identifier(key)
        self.verify()
        if key in self.prefix:
            return self._accepted(self.prefix[key], request, key)
        accepted = self.root / "accepted" / (key + ".json")
        if accepted.exists():
            return self._accepted(load(accepted), request, key)
        prior_failures = self.initial_failures.get(key, [])
        for ref in prior_failures:
            row = self.read(ref)
            self._score(row, request, key)
            require(
                overload(row)["eligible"], "historical failure is not known overload"
            )
        pending = sorted((self.root / "attempts").glob(key + "-a[1-4].json"))
        history = [load(p) for p in pending]
        require(
            [v["attempt"] for v in history]
            == list(
                range(len(prior_failures) + 1, len(prior_failures) + 1 + len(history))
            ),
            "attempt gap or replacement",
        )
        last = prior_failures[-1] if prior_failures else None
        wire_hash = hashlib.sha256(
            route.reservation(request)["request_text"].encode()
        ).hexdigest()
        for record in history:
            require(
                record["logical_id"] == key
                and record["protocol"] == self.protocol
                and record["request_sha256"] == wire_hash
                and record["physical_id"] == key + f"-a{record['attempt']}",
                "durable attempt binding changed",
            )
            if "evidence" not in record:
                # Adapter may have finished a call before the index commit.
                recover = self.root / "calls" / (record["physical_id"] + ".json")
                if not recover.exists():
                    if self.recover_claim is None:
                        raise Paused("admitted_request_without_durable_result")
                    # Adapter MUST prove no reservation/POST exists before
                    # completing an interrupted pre-admission claim.
                    recover = self.recover_claim(record, deepcopy(request))
                ref = self.reference(recover)
            else:
                ref = record["evidence"]
            row = self.read(ref)
            if "evidence" not in record:
                record["evidence"] = ref
                atomic(
                    self.root / "attempts" / (record["physical_id"] + ".json"), record
                )
            score = self._score(row, request, key)
            if score["status"] in (
                "recorded_valid",
                "content_failed",
                "resource_failed",
            ):
                atomic(accepted, ref)
                return self._accepted(ref, request, key)
            if not overload(row)["eligible"]:
                raise Paused("nonretryable_instrument_failure")
            last = ref
        next_attempt = len(prior_failures) + len(history) + 1
        while next_attempt <= 4:
            self.verify()
            if last:
                row = self.read(last)
                verdict = overload(row)
                require(verdict["eligible"], "no content-based retry")
                delay = max(COOLDOWNS[next_attempt - 2], verdict["delay"] or 0)
                not_before = row["ended_unix"] + delay
                while self.clock() < not_before:
                    self.sleep(min(30, not_before - self.clock()))
                self.verify()
            require(
                len(list((self.root / "attempts").glob("*.json")))
                < self.maximum_physical,
                "physical request cap exhausted",
            )
            retries = sum(
                load(p)["attempt"] > 1 for p in (self.root / "attempts").glob("*.json")
            )
            require(
                next_attempt == 1 or retries < self.maximum_reissues,
                "block retry cap exhausted",
            )
            physical_id = key + f"-a{next_attempt}"
            path = self.root / "attempts" / (physical_id + ".json")
            require(not path.exists(), "never repeat a claimed physical attempt")
            record = dict(
                protocol=self.protocol,
                logical_id=key,
                physical_id=physical_id,
                attempt=next_attempt,
                request_sha256=hashlib.sha256(
                    route.reservation(request)["request_text"].encode()
                ).hexdigest(),
            )
            atomic(path, record)
            returned_path = self.perform(deepcopy(request), key, physical_id)
            ref = self.reference(returned_path)
            record["evidence"] = ref
            atomic(path, record)
            row = self.read(ref)
            self.verify()
            score = self._score(row, request, key)
            if score["status"] in (
                "recorded_valid",
                "content_failed",
                "resource_failed",
            ):
                atomic(accepted, ref)
                return self._accepted(ref, request, key)
            if not overload(row)["eligible"]:
                raise Paused("nonretryable_instrument_failure")
            last, next_attempt = ref, next_attempt + 1
        raise Paused("per_action_retry_limit")
