#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request

TARGET_FILE_HINTS = {
    "mac-arm64": ("mac-arm64", "darwin-arm64", "arm64"),
    "mac-x64": ("mac-x64", "darwin-x64", "x64"),
    "win-x64": ("win-x64", "windows-x64", "win32-x64", "x64"),
}


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def required(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def artifact_matches_target(path: Path, target: str) -> bool:
    name = path.name.lower()
    return any(hint in name for hint in TARGET_FILE_HINTS.get(target, (target,)))


def pick_artifact(pattern: str, target: str = "") -> Path:
    paths = [
        Path(item)
        for item in glob.glob(pattern, recursive=True)
        if Path(item).is_file()
    ]
    paths = [item for item in paths if not item.name.endswith((".blockmap", ".yml", ".yaml"))]
    if not paths:
        raise RuntimeError(f"No artifact matched pattern: {pattern}")
    paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if target:
        target_paths = [item for item in paths if artifact_matches_target(item, target)]
        if target_paths:
            return target_paths[0]
        if len(paths) > 1:
            candidates = ", ".join(item.name for item in paths[:8])
            raise RuntimeError(f"Multiple artifacts matched {pattern}, but none looked like {target}: {candidates}")
    return paths[0]


def post_callback(payload: dict) -> None:
    callback_url = required("RELEASE_CALLBACK_URL")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, 4):
        req = request.Request(
            callback_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                if response.status < 300:
                    return
                if response.status not in {408, 429} and response.status < 500:
                    raise RuntimeError(f"Callback failed with status {response.status}")
        except urllib_error.HTTPError as exc:
            retryable = exc.code in {408, 429} or exc.code >= 500
            if not retryable or attempt == 3:
                raise RuntimeError(f"Callback failed with status {exc.code}") from exc
        except (urllib_error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise RuntimeError(f"Callback failed after {attempt} attempts: {exc}") from exc
        time.sleep(2 ** (attempt - 1))


def artifact_upload_url() -> str:
    explicit = env("RELEASE_ARTIFACT_UPLOAD_URL")
    if explicit:
        return explicit
    callback_url = required("RELEASE_CALLBACK_URL")
    if callback_url.endswith("/build-callback"):
        return callback_url[: -len("/build-callback")] + "/build-artifact"
    return callback_url.rstrip("/") + "/build-artifact"


def post_artifact(path: Path, target: str, status: str) -> None:
    try:
        import requests  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Python package 'requests' is required: {exc}") from exc

    data = {
        "token": required("RELEASE_CALLBACK_TOKEN"),
        "releaseId": required("RELEASE_ID"),
        "releaseVersion": required("RELEASE_VERSION"),
        "releaseChannel": required("RELEASE_CHANNEL"),
        "target": target,
        "status": status,
        "buildRunId": env("BUILD_RUN_ID") or env("GITHUB_RUN_ID"),
    }
    optional_verification_fields = {
        "verificationStatus": env("RELEASE_ARTIFACT_VERIFICATION_STATUS"),
        "signatureStatus": env("RELEASE_ARTIFACT_SIGNATURE_STATUS"),
        "smokeStatus": env("RELEASE_ARTIFACT_SMOKE_STATUS"),
        "verificationRunId": env("GITHUB_RUN_ID") or env("BUILD_RUN_ID"),
    }
    data.update({key: value for key, value in optional_verification_fields.items() if value})
    for attempt in range(1, 4):
        try:
            with path.open("rb") as handle:
                response = requests.post(
                    artifact_upload_url(),
                    data=data,
                    files={"file": (path.name, handle, "application/octet-stream")},
                    timeout=1800,
                )
            if response.status_code < 300:
                return
            retryable = response.status_code in {408, 429} or response.status_code >= 500
            if not retryable or attempt == 3:
                raise RuntimeError(f"Artifact upload callback failed with status {response.status_code}: {response.text[:2000]}")
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Artifact upload callback failed after {attempt} attempts: {exc}") from exc
        time.sleep(2 ** (attempt - 1))


def base_payload(status: str) -> dict:
    return {
        "token": required("RELEASE_CALLBACK_TOKEN"),
        "releaseId": required("RELEASE_ID"),
        "releaseVersion": required("RELEASE_VERSION"),
        "releaseChannel": required("RELEASE_CHANNEL"),
        "status": status,
        "buildRunId": env("BUILD_RUN_ID") or env("GITHUB_RUN_ID"),
    }


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MAX_CALLBACK_ERROR_LENGTH = 480


def failure_error(message: str, error_files: list[str]) -> str:
    summary = message.strip()
    for error_file in error_files:
        path = Path(error_file)
        if path.is_file():
            log_text = ANSI_ESCAPE.sub("", path.read_text(encoding="utf-8", errors="replace")).strip()
            if not log_text:
                continue
            separator = "\n" if summary and log_text else ""
            available = max(0, MAX_CALLBACK_ERROR_LENGTH - len(summary) - len(separator))
            log_tail = log_text[-available:] if available else ""
            if log_tail:
                summary = f"{summary}{separator}{log_tail}"
            break
    return summary[-MAX_CALLBACK_ERROR_LENGTH:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, choices=["queued", "building", "uploaded", "succeeded", "failed"])
    parser.add_argument("--target", default="")
    parser.add_argument("--artifact-glob", default="")
    parser.add_argument("--error", default="")
    parser.add_argument("--error-file", action="append", default=[])
    args = parser.parse_args()

    if args.artifact_glob:
        if not args.target:
            raise RuntimeError("--target is required when --artifact-glob is used")
        artifact_path = pick_artifact(args.artifact_glob, args.target)
        post_artifact(artifact_path, args.target, args.status)
    else:
        payload = base_payload(args.status)
        error = failure_error(args.error, args.error_file)
        if error:
            payload["error"] = error
        post_callback(payload)
    print(json.dumps({"ok": True, "status": args.status, "target": args.target}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"release artifact upload failed: {exc}", file=sys.stderr)
        raise
