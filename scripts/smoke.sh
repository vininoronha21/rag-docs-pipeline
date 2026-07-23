#!/usr/bin/env bash
set -euo pipefail

tmp_files=()

cleanup() {
  local file
  if [[ ${#tmp_files[@]} -eq 0 ]]; then
    return
  fi
  for file in "${tmp_files[@]}"; do
    if [[ -n "$file" && -f "$file" ]]; then
      rm -f "$file"
    fi
  done
}
trap cleanup EXIT

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    fail "$name is required."
  fi
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "$name is required."
  fi
}

normalize_url() {
  local url="$1"
  while [[ "$url" == */ ]]; do
    url="${url%/}"
  done
  printf '%s' "$url"
}

make_temp() {
  local result_var="$1"
  local file
  file="$(mktemp)"
  tmp_files+=("$file")
  printf -v "$result_var" '%s' "$file"
}

log_step() {
  printf '%s\n' "$1"
}

post_query() {
  local question="$1"
  local response_file="$2"
  local request_file
  make_temp request_file

  jq -n --arg question "$question" '{question: $question, top_k: 5}' >"$request_file"
  curl --fail --silent --show-error \
    --request POST \
    --header 'Content-Type: application/json' \
    --data-binary "@$request_file" \
    --output "$response_file" \
    "$backend_url/api/query"
}

require_env FRONTEND_URL
require_env BACKEND_URL
require_env SMOKE_ANSWERABLE_QUESTION
require_env SMOKE_UNSUPPORTED_QUESTION
require_command curl
require_command jq

frontend_url="$(normalize_url "$FRONTEND_URL")"
backend_url="$(normalize_url "$BACKEND_URL")"
if [[ -z "$frontend_url" ]]; then
  fail "FRONTEND_URL is required."
fi
if [[ -z "$backend_url" ]]; then
  fail "BACKEND_URL is required."
fi

cold_start_curl=(curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 10)
direct_curl=(curl --fail --silent --show-error)

make_temp health_response
make_temp ready_response
make_temp answered_response
make_temp unsupported_response

log_step "Checking frontend availability."
"${direct_curl[@]}" --output /dev/null "$frontend_url"

log_step "Checking backend health."
"${cold_start_curl[@]}" --output "$health_response" "$backend_url/api/health"
jq -e '.status | type == "string"' "$health_response" >/dev/null || \
  fail "Backend health did not satisfy the response contract."

log_step "Checking backend readiness."
"${cold_start_curl[@]}" --output "$ready_response" "$backend_url/api/ready"
jq -e '.status == "ready" and .database == "ok" and .pgvector == "ok"' "$ready_response" \
  >/dev/null || fail "Backend readiness did not satisfy the response contract."

log_step "Checking public answered query contract."
post_query "$SMOKE_ANSWERABLE_QUESTION" "$answered_response"
jq -e '
  def optional_bool($name; $value): ((has($name) | not) or .[$name] == $value);
  (.event_id | type == "string" and test("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"))
  and .state == "answered"
  and optional_bool("answered"; true)
  and optional_bool("insufficient_evidence"; false)
  and (.answer | type == "object")
  and (.answer.sentences | type == "array" and length > 0)
  and (.evidence | type == "array" and length > 0)
  and all(
    .answer.sentences[];
    (.text | type == "string" and length > 0)
    and (.citation_id | type == "string" and length > 0)
  )
  and all(
    .evidence[];
    (.citation_id == null or (.citation_id | type == "string"))
    and (.commit_sha | type == "string" and test("^[0-9a-fA-F]{40}$"))
    and (.commit_sha as $sha | (.source_url | type == "string" and contains("/blob/" + $sha + "/")))
  )
  and ([.evidence[] | select(.citation_id != null) | .citation_id] as $citation_ids
    | all(.answer.sentences[]; .citation_id as $citation_id | ($citation_ids | index($citation_id) != null)))
' "$answered_response" >/dev/null || \
  fail "Answered smoke query did not satisfy the response contract."

log_step "Checking public unsupported query contract."
post_query "$SMOKE_UNSUPPORTED_QUESTION" "$unsupported_response"
jq -e '
  def optional_bool($name; $value): ((has($name) | not) or .[$name] == $value);
  (.event_id | type == "string" and test("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"))
  and .state == "insufficient_evidence"
  and optional_bool("answered"; false)
  and optional_bool("insufficient_evidence"; true)
  and (.answer == null or (.answer.sentences | type == "array" and length == 0))
  and (.evidence | type == "array")
' "$unsupported_response" >/dev/null || \
  fail "Unsupported smoke query did not return insufficient_evidence."

log_step "Checking admin authentication boundary."
admin_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "$backend_url/api/admin/sources")"
if [[ "$admin_status" != "401" ]]; then
  fail "Admin unauthorized smoke check did not return 401."
fi

log_step "Smoke checks passed."
