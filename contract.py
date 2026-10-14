# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import datetime
import json
from genlayer import *

@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass

class FirstFixBounty(gl.Contract):
    poster_map: TreeMap[str, Address]
    description_map: TreeMap[str, str]
    repo_url_map: TreeMap[str, str]
    pool_map: TreeMap[str, u256]
    status_map: TreeMap[str, str]
    winner_map: TreeMap[str, Address]
    winning_fix_url_map: TreeMap[str, str]
    reasoning_map: TreeMap[str, str]
    attempt_count_map: TreeMap[str, u256]
    deadline_map: TreeMap[str, str]
    bounty_counter: u256

    def __init__(self):
        self.bounty_counter = u256(0)

    @gl.public.write.payable
    def post_bug(self, bug_description: str, repo_url: str, minutes_until_deadline: int) -> str:
        assert gl.message.value > u256(0), "You must fund the bounty with a positive amount"

        bounty_id = f"F{self.bounty_counter}"
        self.bounty_counter += u256(1)

        self.poster_map[bounty_id] = gl.message.sender_address
        self.description_map[bounty_id] = bug_description
        self.repo_url_map[bounty_id] = repo_url
        self.pool_map[bounty_id] = gl.message.value
        self.status_map[bounty_id] = "OPEN"
        self.winning_fix_url_map[bounty_id] = ""
        self.reasoning_map[bounty_id] = ""
        self.attempt_count_map[bounty_id] = u256(0)
        self.deadline_map[bounty_id] = str(datetime.datetime.now() + datetime.timedelta(minutes=minutes_until_deadline))

        return bounty_id

    @gl.public.write
    def cancel_bug(self, bounty_id: str) -> None:
        assert gl.message.sender_address == self.poster_map[bounty_id], "Only the poster can cancel"
        assert self.status_map[bounty_id] == "OPEN", "Bounty not open"

        pool = self.pool_map[bounty_id]
        self.status_map[bounty_id] = "CANCELLED"
        _Recipient(self.poster_map[bounty_id]).emit_transfer(value=pool)

    @gl.public.write
    def claim_timeout_refund(self, bounty_id: str) -> None:
        assert self.status_map[bounty_id] == "OPEN", "Bounty already closed or cancelled"
        assert str(datetime.datetime.now()) >= self.deadline_map[bounty_id], "Deadline has not passed yet"

        pool = self.pool_map[bounty_id]
        self.status_map[bounty_id] = "TIMED_OUT"
        _Recipient(self.poster_map[bounty_id]).emit_transfer(value=pool)

    @gl.public.write
    def submit_fix(self, bounty_id: str, fix_url: str) -> str:
        assert self.status_map[bounty_id] == "OPEN", "Bounty already closed - a valid fix was already accepted, or it was cancelled/timed out"
        assert str(datetime.datetime.now()) < self.deadline_map[bounty_id], "Deadline has passed"

        self.attempt_count_map[bounty_id] = self.attempt_count_map[bounty_id] + u256(1)

        description = self.description_map[bounty_id]
        repo_url = self.repo_url_map[bounty_id]

        def judge() -> str:
            repo_content = gl.nondet.web.render(repo_url, mode="text")
            fix_content = gl.nondet.web.render(fix_url, mode="text")
            prompt = f"""You are verifying whether a submitted fix genuinely resolves a described bug.

Bug description:
\"\"\"{description}\"\"\"

Original buggy code / reference content:
\"\"\"{repo_content[:3000]}\"\"\"

Submitted fix content:
\"\"\"{fix_content[:3000]}\"\"\"

Based strictly on the submitted fix content, does it genuinely and correctly
resolve the described bug?

Respond with strict JSON only, no markdown, no extra text:
{{"verdict": "VALID_FIX", "reasoning": "<one sentence>"}}
or
{{"verdict": "INVALID_FIX", "reasoning": "<one sentence>"}}
"""
            return gl.nondet.exec_prompt(prompt)

        raw = gl.eq_principle.prompt_comparative(
            judge,
            "The verdict field must match exactly (VALID_FIX or INVALID_FIX). Reasoning wording may vary but must express the same underlying judgment.",
        )

        try:
            parsed = json.loads(raw)
        except Exception:
            raise Exception("Verifier output was not valid JSON; refusing to accept this submission.")

        assert isinstance(parsed, dict), "Verifier output was not a JSON object; refusing to accept this submission."
        assert "verdict" in parsed, "Verifier output missing 'verdict' field; refusing to accept this submission."
        verdict = parsed["verdict"]
        assert isinstance(verdict, str), "Verifier 'verdict' field was not a string; refusing to accept this submission."
        assert verdict in ("VALID_FIX", "INVALID_FIX"), "Verifier 'verdict' was outside the allowed domain; refusing to accept this submission."

        reasoning = parsed.get("reasoning", "")
        assert isinstance(reasoning, str), "Verifier 'reasoning' field was not a string; refusing to accept this submission."

        if verdict == "VALID_FIX":
            pool = self.pool_map[bounty_id]
            self.status_map[bounty_id] = "CLOSED"
            self.winner_map[bounty_id] = gl.message.sender_address
            self.winning_fix_url_map[bounty_id] = fix_url
            self.reasoning_map[bounty_id] = reasoning
            _Recipient(gl.message.sender_address).emit_transfer(value=pool)
            return f"VALID_FIX - you won the bounty, paid {pool} wei"
        else:
            return f"INVALID_FIX - {reasoning}"

    @gl.public.view
    def get_bounty(self, bounty_id: str) -> dict:
        try:
            winner = str(self.winner_map[bounty_id])
        except Exception:
            winner = "NONE"
        return {
            "bounty_id": bounty_id,
            "poster": str(self.poster_map[bounty_id]),
            "description": self.description_map[bounty_id],
            "repo_url": self.repo_url_map[bounty_id],
            "pool": str(self.pool_map[bounty_id]),
            "status": self.status_map[bounty_id],
            "winner": winner,
            "winning_fix_url": self.winning_fix_url_map[bounty_id],
            "reasoning": self.reasoning_map[bounty_id],
            "attempt_count": str(self.attempt_count_map[bounty_id]),
            "deadline": self.deadline_map[bounty_id],
        }

    @gl.public.view
    def get_bounty_count(self) -> int:
        return int(self.bounty_counter)
