import argparse
import base64
from datetime import datetime, timezone
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple, Union


def load_env(env_path: str = ".env") -> Dict[str, str]:
    """Parses key-value pairs from a .env file without external libraries.

    Supports comments (#), empty lines, quoted values, and export prefixes.
    """
    env_vars: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[7:].strip()

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]

                env_vars[key] = val

    return env_vars


def get_elastic_credentials(env_path: str = ".env") -> Tuple[str, str, str, str]:
    """Resolves Elasticsearch connection settings and credentials.

    Priority order:
      1. Environment variables already set in os.environ
      2. Key-value pairs in the specified .env file
      3. Safe local defaults (https://localhost:9200)

    Returns:
      (es_url, api_key, username, password)
    """
    env = {}
    for candidate in [env_path, ".env"]:
        if os.path.exists(candidate):
            env = load_env(candidate)
            break

    # 1. Resolve Elasticsearch base URL
    es_url = os.environ.get("ES_URL") or env.get("ES_URL")
    if not es_url:
        kibana_url = os.environ.get("KIBANA_URL") or env.get("KIBANA_URL")
        if kibana_url:
            parsed = urllib.parse.urlparse(kibana_url)
            hostname = parsed.hostname or "localhost"
            es_url = f"https://{hostname}:9200"
        else:
            es_url = "https://localhost:9200"

    # 2. Resolve Authentication (API Key takes precedence over Basic Auth)
    api_key = (
        os.environ.get("ES_API_KEY")
        or env.get("ES_API_KEY")
        or os.environ.get("KIBANA_API_KEY")
        or env.get("KIBANA_API_KEY")
        or ""
    )

    user = os.environ.get("ES_USER") or env.get("ES_USER") or os.environ.get("ELASTIC_USER") or ""
    password = (
        os.environ.get("ES_PASSWORD")
        or env.get("ES_PASSWORD")
        or os.environ.get("ELASTIC_PASSWORD")
        or env.get("ELASTIC_PASSWORD")
        or ""
    )

    return es_url.rstrip("/"), api_key, user, password


def elastic_request(
    endpoint: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    es_url: Optional[str] = None,
    api_key: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = False,
    timeout: int = 30,
) -> Tuple[int, Union[Dict[str, Any], str]]:
    """Performs an authenticated HTTP request against Elasticsearch.

    Args:
        endpoint: Target API path (e.g., '/_license', '/_license/start_trial?acknowledge=true')
        method: HTTP method (GET, POST, etc.)
        body: Optional JSON request payload
        es_url: Elasticsearch base URL
        api_key: Elasticsearch API key
        user: Basic auth username
        password: Basic auth password
        verify_ssl: Enforce strict TLS certificate checks
        timeout: Request timeout in seconds

    Returns:
        (status_code, parsed_json_or_text_response)
    """
    if not es_url or (not api_key and not (user and password)):
        auto_url, auto_key, auto_user, auto_pwd = get_elastic_credentials()
        es_url = es_url or auto_url
        api_key = api_key if api_key is not None else auto_key
        user = user if user is not None else auto_user
        password = password if password is not None else auto_pwd

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    url = f"{es_url}{endpoint}"

    req_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Elastic-Trial-Activator/1.0",
    }

    if api_key:
        req_headers["Authorization"] = f"ApiKey {api_key}"
    elif user and password:
        auth_bytes = f"{user}:{password}".encode("utf-8")
        req_headers["Authorization"] = f"Basic {base64.b64encode(auth_bytes).decode('ascii')}"

    ssl_ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()

    encoded_body = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=encoded_body, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as resp:
            status_code = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw_body = resp.read().decode("utf-8", errors="replace")

            if "json" in content_type.lower():
                try:
                    return status_code, json.loads(raw_body)
                except json.JSONDecodeError:
                    return status_code, raw_body
            return status_code, raw_body

    except urllib.error.HTTPError as e:
        status_code = e.code
        raw_body = e.read().decode("utf-8", errors="replace")
        try:
            return status_code, json.loads(raw_body)
        except Exception:
            return status_code, raw_body

    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to Elasticsearch at {url}: {e.reason}") from e


def get_license_info(
    es_url: Optional[str] = None,
    api_key: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """Fetches the current cluster license information.

    Returns:
        Dict representing current license details from `GET /_license`.
    """
    status, response = elastic_request(
        endpoint="/_license",
        method="GET",
        es_url=es_url,
        api_key=api_key,
        user=user,
        password=password,
        verify_ssl=verify_ssl,
    )
    if status != 200:
        raise RuntimeError(f"Failed to query /_license (HTTP {status}): {response}")
    return response if isinstance(response, dict) else {"raw": response}


def check_trial_eligibility(
    es_url: Optional[str] = None,
    api_key: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """Checks whether the cluster is eligible to start a 30-day trial.

    Returns:
        Dict containing `eligible_to_start_trial` (bool) from `GET /_license/trial_status`.
    """
    status, response = elastic_request(
        endpoint="/_license/trial_status",
        method="GET",
        es_url=es_url,
        api_key=api_key,
        user=user,
        password=password,
        verify_ssl=verify_ssl,
    )
    if status != 200:
        raise RuntimeError(f"Failed to query /_license/trial_status (HTTP {status}): {response}")
    return response if isinstance(response, dict) else {"raw": response}


def start_elastic_trial(
    acknowledge: bool = True,
    es_url: Optional[str] = None,
    api_key: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """Initiates a 30-day trial license in Elasticsearch.

    Calls `POST /_license/start_trial?acknowledge=true`.

    Returns:
        Dict containing the API response, e.g. {"trial_was_started": True, "acknowledged": True}
    """
    endpoint = f"/_license/start_trial?acknowledge={'true' if acknowledge else 'false'}"
    status, response = elastic_request(
        endpoint=endpoint,
        method="POST",
        es_url=es_url,
        api_key=api_key,
        user=user,
        password=password,
        verify_ssl=verify_ssl,
    )

    if status != 200:
        error_details = response.get("error", {}).get("reason", str(response)) if isinstance(response, dict) else response
        raise RuntimeError(f"Failed to start trial (HTTP {status}): {error_details}")

    return response if isinstance(response, dict) else {"raw": response}


def format_expiry(timestamp_millis: Optional[int]) -> str:
    """Formats epoch milliseconds into a human-readable string with remaining time."""
    if not timestamp_millis or timestamp_millis <= 0:
        return "N/A (Never / Unlimited)"

    expiry_dt = datetime.fromtimestamp(timestamp_millis / 1000.0, tz=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    diff = expiry_dt - now_dt

    formatted_date = expiry_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    if diff.total_seconds() > 0:
        days = diff.days
        hours = int(diff.seconds // 3600)
        return f"{formatted_date} ({days} days, {hours} hours remaining)"
    else:
        return f"{formatted_date} (EXPIRED)"


def run(
    check_only: bool = False,
    output_json: bool = False,
    env_file: str = ".env",
    es_url: Optional[str] = None,
    api_key: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: bool = False,
) -> int:
    """Executes the trial check and activation flow."""
    # Resolve connection info
    resolved_url, auto_key, auto_user, auto_pwd = get_elastic_credentials(env_path=env_file)
    target_url = es_url or resolved_url
    target_key = api_key if api_key is not None else auto_key
    target_user = user if user is not None else auto_user
    target_pwd = password if password is not None else auto_pwd

    if not output_json:
        print(f"[*] Target Elasticsearch URL: {target_url}")

    # 1. Fetch current license
    try:
        current_lic_data = get_license_info(
            es_url=target_url,
            api_key=target_key,
            user=target_user,
            password=target_pwd,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        if output_json:
            print(json.dumps({"success": False, "error": f"Failed to get current license: {e}"}))
        else:
            print(f"[-] Error querying current license: {e}", file=sys.stderr)
        return 1

    lic_info = current_lic_data.get("license", {})
    lic_type = lic_info.get("type", "unknown").lower()
    lic_status = lic_info.get("status", "unknown")
    expiry_ms = lic_info.get("expiry_date_in_millis")

    if not output_json:
        print(f"[*] Current License Type:   {lic_type.upper()}")
        print(f"[*] Current License Status: {lic_status}")
        print(f"[*] Current Expiry:         {format_expiry(expiry_ms)}")

    # 2. Check trial eligibility
    try:
        eligibility_data = check_trial_eligibility(
            es_url=target_url,
            api_key=target_key,
            user=target_user,
            password=target_pwd,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        if output_json:
            print(json.dumps({"success": False, "error": f"Failed to check trial eligibility: {e}"}))
        else:
            print(f"[-] Error checking trial eligibility: {e}", file=sys.stderr)
        return 1

    is_eligible = bool(eligibility_data.get("eligible_to_start_trial", False))

    if check_only:
        summary = {
            "license": lic_info,
            "eligible_to_start_trial": is_eligible,
        }
        if output_json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"[*] Eligible to start trial: {is_eligible}")
        return 0

    # 3. Handle already active trial / enterprise license
    if lic_type == "trial" and lic_status == "active":
        msg = f"Cluster already has an active 30-day trial license expiring on {format_expiry(expiry_ms)}."
        if output_json:
            print(json.dumps({"success": True, "message": msg, "license": lic_info}))
        else:
            print(f"[+] {msg}")
        return 0

    if not is_eligible:
        err_msg = (
            "Cluster is not eligible to start a trial license. "
            "A trial may have already been activated previously on this cluster for the current major version."
        )
        if output_json:
            print(json.dumps({"success": False, "error": err_msg, "license": lic_info}))
        else:
            print(f"[-] {err_msg}", file=sys.stderr)
        return 1

    # 4. Start the trial
    if not output_json:
        print("[*] Initiating 30-day Elastic Trial (POST /_license/start_trial?acknowledge=true)...")

    try:
        start_result = start_elastic_trial(
            acknowledge=True,
            es_url=target_url,
            api_key=target_key,
            user=target_user,
            password=target_pwd,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        if output_json:
            print(json.dumps({"success": False, "error": f"Failed to activate trial: {e}"}))
        else:
            print(f"[-] Activation failed: {e}", file=sys.stderr)
        return 1

    # 5. Verify the new license
    try:
        new_lic_data = get_license_info(
            es_url=target_url,
            api_key=target_key,
            user=target_user,
            password=target_pwd,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        new_lic_data = {"error": f"Trial started but failed to re-query license: {e}"}

    new_lic = new_lic_data.get("license", {})
    new_expiry_ms = new_lic.get("expiry_date_in_millis")

    if output_json:
        print(json.dumps({
            "success": True,
            "start_trial_response": start_result,
            "new_license": new_lic,
        }, indent=2))
    else:
        print("[+] Trial successfully activated!")
        print(f"    - License Type:   {new_lic.get('type', 'trial').upper()}")
        print(f"    - Status:         {new_lic.get('status', 'active')}")
        print(f"    - Expiry Date:    {format_expiry(new_lic_expiry_ms := new_expiry_ms)}")
        print(f"    - Issued To:      {new_lic.get('issued_to')}")
        print(f"    - UID:            {new_lic.get('uid')}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Programmatically start or check an Elastic 30-day trial license.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check current license status and trial eligibility without activating.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env configuration file.",
    )
    parser.add_argument(
        "--es-url",
        default=None,
        help="Override Elasticsearch base URL (defaults to ES_URL or KIBANA_URL from .env).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override API key for authentication.",
    )
    parser.add_argument(
        "-u", "--user",
        default=None,
        help="Basic auth username.",
    )
    parser.add_argument(
        "-p", "--password",
        default=None,
        help="Basic auth password.",
    )
    parser.add_argument(
        "-k", "--insecure",
        action="store_true",
        default=True,
        help="Disable SSL certificate verification (default True for self-signed certs).",
    )
    parser.add_argument(
        "--verify-ssl",
        dest="insecure",
        action="store_false",
        help="Enforce strict SSL certificate verification.",
    )

    args = parser.parse_args()

    exit_code = run(
        check_only=args.check,
        output_json=args.json,
        env_file=args.env_file,
        es_url=args.es_url,
        api_key=args.api_key,
        user=args.user,
        password=args.password,
        verify_ssl=not args.insecure,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
