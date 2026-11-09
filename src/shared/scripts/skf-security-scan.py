# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Security Scan: the optional Snyk Agent Scan of a written skill package.

Quick Skill, Create Skill, Update Skill and Create Stack Skill scan the skill
package they wrote for prompt injection and the other risks Snyk Agent Scan
reports. The scan needs a Snyk API token in SNYK_TOKEN and sends the skill's
files, with the machine's host name and user name, to Snyk's analysis
server, so it runs only when that variable is set.
This helper owns every decision around the scan, so the step files hold no
scanner command and no rule for reading its output:

  run    check SNYK_TOKEN, run the scanner on the package at the version
         SCANNER_SPEC pins, and print one JSON result.
  parse  read a saved scanner stdout and exit code the way run reads them
         (for tests, and for reading a scan again by hand).

Why not through skill-check: skill-check 1.2.0 runs the scanner without
--ci, writes its --format json output before the scan starts, and counts as
findings only bracketed codes such as [E001], which snyk-agent-scan 0.6
never prints for a risk. So whatever the scanner found, a `skill-check
check --format json` run never showed it (#892). The scanner's own --json
output carries each risk with its score and evidence, and each analysis
error, so this helper reads that, never the exit code alone: without --ci
the scanner exits 0 when it finds risks, and also when its analysis fails
(a 401 for a bad token, a 429 at the daily limit).

The command, run with no stdin in a process group of its own through the
runner of skf-source-tree.py (the sibling in this folder), which kills the
whole group when the time limit passes:

  uvx <SCANNER_SPEC> --json --skills <package>

The limit (--timeout, DEFAULT_TIMEOUT_SEC) keeps the call, the kill
included, inside the two minutes some shell tools allow one command. A
first run also installs the scanner through uvx, which can take part of
that time.

Output (stdout, one JSON object with every key in RESULT_KEYS):
  security_result  pass, warn or skipped
  scanner          SCANNER_SPEC
  findings         one entry per risk the scanner reported:
                   {skill, risk, name, score, evidence, text}, where skill is
                   the skill (or MCP server) the risk is in, risk the
                   scanner's key, name its display name, score 0-1000 or
                   null, and text the one line the reports record
  errors           the message of each analysis error the scanner reported
  note             one line the step files record with security_result

security_result, from the first rule that applies:
  skipped  SNYK_TOKEN is unset or blank (nothing is started), uvx is not
           on PATH, the scanner could not start or did not finish within
           the time limit
  warn     the scanner's JSON holds a risk, whatever its exit code
  skipped  the scanner exited non-zero, its stdout is not the scanner's
           JSON, it reported an analysis error (such as a 401 or a 429),
           or it found no skill in the package
  pass     otherwise: the scanner analysed the package and reported no risk

Exit codes:
  0  a result was printed (every security_result)
  2  usage error (argparse), such as a package that is not a folder

CLI (stdlib only):
  uv run skf-security-scan.py run --package <skill-dir> [--timeout SEC]
  uv run skf-security-scan.py parse --stdout-file <file> --exit-code <n> [--stderr-file <file>]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

# Bump with care: classify() reads the response models of this version
# (agent_scan.models.api.v20260710 in snyk-agent-scan 0.6.11), and
# tool-requirements.yaml names it in the snyk_agent_scan basis.
SCANNER_SPEC = "snyk-agent-scan@0.6.11"
TOKEN_ENV = "SNYK_TOKEN"
DEFAULT_TIMEOUT_SEC = 110
RESULT_KEYS = ("security_result", "scanner", "findings", "errors", "note")
MAX_LINE = 300
# The display names snyk-agent-scan 0.6.11 gives its risk keys
# (MCP_SERVER_RISK_DISPLAY_NAMES and SKILL_RISK_DISPLAY_NAMES). A key not
# listed here is shown as it is.
RISK_NAMES = {
    "prompt_injection_tool_desc": "Prompt injection in tool",
    "untrusted_content": "Untrusted content",
    "private_data": "Private data",
    "destructive_capabilities": "Destructive capabilities",
    "prompt_injection_skill_instructions": "Potential prompt injection",
    "suspicious_download_url": "Suspicious download URL",
    "malicious_code": "Malicious code",
    "insecure_credential_handling": "Insecure credential handling",
    "secret_detection": "Secret detection",
    "direct_money_access": "Direct money access",
    "third_party_content_exposure": "Third party content exposure",
    "unverifiable_dependencies": "Unverifiable dependencies",
    "modifying_system_services": "Attempt to modify system services",
    "missing_skill_md": "Missing SKILL.md",
}
RISK_SCORE_MAX = 1000
_SPACES = re.compile(r"\s+")
_SIBLING = None


def _sibling():
    """skf-source-tree.py from this folder, loaded once: the scanner runs
    through its runner (_run gives the call its own process group and stops
    all of it at the time limit), and _resolve_outside_cwd never takes a
    uvx planted in the current folder."""
    global _SIBLING
    if _SIBLING is None:
        path = Path(__file__).resolve().parent / "skf-source-tree.py"
        spec = importlib.util.spec_from_file_location("skf_source_tree", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLING = module
    return _SIBLING


def _one_line(text: str) -> str:
    """text on one line, cut to MAX_LINE characters."""
    flat = _SPACES.sub(" ", text or "").strip()
    return flat if len(flat) <= MAX_LINE else flat[:MAX_LINE - 3].rstrip() + "..."


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return _one_line(lines[-1]) if lines else ""


def result(security_result: str, note: str, findings: list | None = None, errors: list | None = None) -> dict:
    return {"security_result": security_result, "scanner": SCANNER_SPEC, "findings": findings or [],
            "errors": errors or [], "note": note}


def token_configured(env: dict | None = None) -> bool:
    """True when SNYK_TOKEN holds more than whitespace (skf-detect-tools.py's probe_security_scan rule)."""
    return bool((os.environ if env is None else env).get(TOKEN_ENV, "").strip())


def scanner_command(uvx: str, package: Path) -> list[str]:
    return [uvx, SCANNER_SPEC, "--json", "--skills", os.path.abspath(package)]


def _find_uvx() -> str | None:
    return _sibling()._resolve_outside_cwd("uvx")


def _scan(argv: list[str], timeout: float) -> tuple[int | None, bytes, bytes]:
    """Run argv; (returncode, stdout, stderr), returncode None when the time limit stopped it."""
    returncode, stdout, stderr, _killed = _sibling()._run(argv, timeout)
    return returncode, stdout, stderr


def parse_response(stdout: str):
    """The scanner's JSON object, or None when stdout holds none.

    The JSON is all the scanner prints with --json; a stray line before it
    is skipped, so the object is read from the first line that opens one.
    """
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = text.find("\n{")
    if start == -1:
        return None
    try:
        value, _end = json.JSONDecoder().raw_decode(text[start + 1:])
    except ValueError:
        return None
    return value


def _recognized(response) -> bool:
    paths = response.get("scan_path_responses") if isinstance(response, dict) else None
    return isinstance(paths, list) and all(isinstance(path, dict) for path in paths)


def _entries(path: dict, key: str) -> list[dict]:
    value = path.get(key)
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _finding(component: str, risk: str, value) -> dict:
    details = value if isinstance(value, dict) else {}
    score = details.get("score")
    score = score if isinstance(score, int) and not isinstance(score, bool) else None
    evidence = details.get("evidence") if isinstance(details.get("evidence"), str) else ""
    name = RISK_NAMES.get(risk, risk)
    shown = f"{score}/{RISK_SCORE_MAX}" if score is not None else f"?/{RISK_SCORE_MAX}"
    text = f"{name} ({shown}) in {component}" + (f": {evidence}" if evidence.strip() else "")
    return {"skill": component, "risk": risk, "name": name, "score": score, "evidence": evidence,
            "text": _one_line(text)}


def _error_message(error) -> str | None:
    """The message of a failure error (is_failure true or absent, as the model's default), else None."""
    if not isinstance(error, dict) or error.get("is_failure", True) is False:
        return None
    for key in ("message", "exception", "category"):
        if isinstance(error.get(key), str) and error[key].strip():
            return _one_line(error[key])
    return "unknown error"


def read_response(response: dict) -> tuple[list[dict], list[str], int]:
    """(findings, errors, components) from a recognized response, in the scanner's order."""
    findings, errors, components = [], [], 0
    for path in response["scan_path_responses"]:
        message = _error_message(path.get("error"))
        if message:
            errors.append(message)
        for key in ("skill_risks", "server_risks"):
            for entry in _entries(path, key):
                components += 1
                name = entry.get("name") if isinstance(entry.get("name"), str) else "?"
                indexes = entry.get("risk_indexes")
                if isinstance(indexes, dict):
                    findings.extend(_finding(name, risk, value) for risk, value in indexes.items()
                                    if value is not None)
                message = _error_message(entry.get("error"))
                if message:
                    errors.append(message)
    return findings, errors, components


def classify(returncode: int | None, stdout: str, stderr: str, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict:
    """The result for one scanner run; returncode None means the time limit stopped it."""
    if returncode is None:
        return result("skipped", f"scanner did not finish within {timeout:g} s")
    response = parse_response(stdout)
    recognized = _recognized(response)
    findings, errors, components = read_response(response) if recognized else ([], [], 0)
    if findings:
        count = len(findings)
        note = f"the scanner reported {count} risk" + ("" if count == 1 else "s")
        if errors:
            note += f"; it could not analyse part of the package ({errors[0]})"
        return result("warn", note, findings, errors)
    if returncode != 0:
        line = _last_line(stderr)
        note = f"scanner could not run ({line})" if line else f"scanner exited {returncode} with no output"
        return result("skipped", note, errors=errors)
    if not recognized:
        return result("skipped", "scanner output not recognized")
    if errors:
        return result("skipped", f"scanner could not analyse the package ({errors[0]})", errors=errors)
    if components == 0:
        return result("skipped", "scanner found no skill")
    return result("pass", "the scanner reported no risk")


def run_scan(package: Path, timeout: float = DEFAULT_TIMEOUT_SEC, env: dict | None = None) -> dict:
    """Scan package when SNYK_TOKEN is set; the result, never an exception."""
    if not token_configured(env):
        return result("skipped", f"{TOKEN_ENV} not configured")
    uvx = _find_uvx()
    if uvx is None:
        return result("skipped", "uvx not found")
    try:
        returncode, stdout, stderr = _scan(scanner_command(uvx, package), timeout)
    except (OSError, ValueError) as exc:
        return result("skipped", f"scanner could not start ({_one_line(str(exc))})")
    return classify(returncode, stdout.decode("utf-8", errors="replace"),
                    stderr.decode("utf-8", errors="replace"), timeout)


def _positive(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {value}") from None
    if not seconds > 0:
        raise argparse.ArgumentTypeError(f"must be above 0: {value}")
    return seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or read the optional Snyk Agent Scan of a skill package.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="scan a skill package when SNYK_TOKEN is set")
    run.add_argument("--package", required=True, help="the skill package folder (the one holding SKILL.md)")
    run.add_argument("--timeout", type=_positive, default=DEFAULT_TIMEOUT_SEC,
                     help=f"seconds the scanner may run (default {DEFAULT_TIMEOUT_SEC})")
    parse = sub.add_parser("parse", help="read a saved scanner stdout and exit code")
    parse.add_argument("--stdout-file", required=True)
    parse.add_argument("--exit-code", required=True, type=int)
    parse.add_argument("--stderr-file")
    args = parser.parse_args(argv)
    if args.command == "run":
        package = Path(args.package)
        if not package.is_dir():
            parser.error(f"--package is not a folder: {args.package}")
        out = run_scan(package, args.timeout)
    else:
        try:
            stdout = Path(args.stdout_file).read_text(encoding="utf-8", errors="replace")
            stderr = Path(args.stderr_file).read_text(encoding="utf-8", errors="replace") if args.stderr_file else ""
        except OSError as exc:
            parser.error(f"cannot read {exc.filename}: {exc.strerror}")
        out = classify(args.exit_code, stdout, stderr)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
