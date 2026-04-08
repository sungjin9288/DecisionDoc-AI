#!/bin/bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
STAGE=""
SOURCE_FILE=""
OUTPUT_FILE=".github-actions.env"
FORCE=0

usage() {
  cat <<EOF
Usage: ./$SCRIPT_NAME --stage <dev|prod> [options]

Options:
  --source <path>           Load values from a dotenv-formatted source file
  --output <path>           Output file to create or update (default: .github-actions.env)
  --force                   Recreate the output file from the example template
  -h, --help                Show this help message

Examples:
  bash scripts/$SCRIPT_NAME --stage dev --source .env
  bash scripts/$SCRIPT_NAME --stage dev --source .env --output /tmp/github-actions.env
  bash scripts/$SCRIPT_NAME --stage prod --source .env.prod --force
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      STAGE=${2:-}
      shift 2
      ;;
    --source)
      SOURCE_FILE=${2:-}
      shift 2
      ;;
    --output)
      OUTPUT_FILE=${2:-}
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$STAGE" != "dev" && "$STAGE" != "prod" ]]; then
  echo "ERROR: --stage must be one of: dev, prod" >&2
  usage >&2
  exit 1
fi

if [[ -z "$SOURCE_FILE" ]]; then
  if [[ -f .env ]]; then
    SOURCE_FILE=".env"
  else
    echo "ERROR: --source is required when .env is not present." >&2
    exit 1
  fi
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "ERROR: source env file not found: $SOURCE_FILE" >&2
  exit 1
fi

TEMPLATE_FILE="$SCRIPT_DIR/github-actions.env.example"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "ERROR: template file not found: $TEMPLATE_FILE" >&2
  exit 1
fi

if [[ ! -f "$OUTPUT_FILE" || "$FORCE" -eq 1 ]]; then
  cp "$TEMPLATE_FILE" "$OUTPUT_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$SOURCE_FILE"
set +a

STAGE_UPPER=$(printf '%s' "$STAGE" | tr '[:lower:]' '[:upper:]')
UPDATED=()
PRESERVED=()
SKIPPED=()
UNRESOLVED=()

resolve_value() {
  local name
  for name in "$@"; do
    if [[ -n "${!name-}" ]]; then
      printf '%s' "${!name}"
      return 0
    fi
  done
  return 1
}

set_output_value() {
  local name=$1
  local value=$2
  local tmp
  tmp=$(mktemp "${TMPDIR:-/tmp}/github-actions-env.XXXXXX")
  awk -v key="$name" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      replaced = 1
      next
    }
    { print }
    END {
      if (replaced == 0) {
        print key "=" value
      }
    }
  ' "$OUTPUT_FILE" > "$tmp"
  mv "$tmp" "$OUTPUT_FILE"
}

has_existing_output_value() {
  local name=$1
  local current
  current=$(awk -F= -v key="$name" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' "$OUTPUT_FILE")
  [[ -n "$current" ]]
}

is_local_only_url() {
  local value=$1
  [[ "$value" =~ ^https?://(localhost|127\.[0-9]+\.[0-9]+\.[0-9]+|0\.0\.0\.0)(:[0-9]+)?([/?#].*)?$ ]]
}

copy_value() {
  local target_name=$1
  shift
  local source_value
  if source_value=$(resolve_value "$@"); then
    if [[ "$target_name" == VOICE_BRIEF_API_BASE_URL_* ]] && is_local_only_url "$source_value"; then
      SKIPPED+=("$target_name")
    elif [[ "$target_name" == OPENAI_API_BASE_URL_* ]] && is_local_only_url "$source_value"; then
      SKIPPED+=("$target_name")
    else
      set_output_value "$target_name" "$source_value"
      UPDATED+=("$target_name")
    fi
  elif has_existing_output_value "$target_name"; then
    PRESERVED+=("$target_name")
  else
    UNRESOLVED+=("$target_name")
  fi
}

copy_value AWS_REGION AWS_REGION
copy_value DECISIONDOC_API_KEY DECISIONDOC_API_KEY
copy_value DECISIONDOC_API_KEYS DECISIONDOC_API_KEYS
copy_value DECISIONDOC_OPS_KEY DECISIONDOC_OPS_KEY
copy_value STATUSPAGE_PAGE_ID STATUSPAGE_PAGE_ID
copy_value STATUSPAGE_API_KEY STATUSPAGE_API_KEY

copy_value "AWS_ROLE_ARN_${STAGE_UPPER}" "AWS_ROLE_ARN_${STAGE_UPPER}"
copy_value "DECISIONDOC_S3_BUCKET_${STAGE_UPPER}" "DECISIONDOC_S3_BUCKET_${STAGE_UPPER}" DECISIONDOC_S3_BUCKET
copy_value "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_${STAGE_UPPER}" "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_${STAGE_UPPER}" DECISIONDOC_PROCUREMENT_COPILOT_ENABLED
copy_value "OPENAI_API_KEY_${STAGE_UPPER}" "OPENAI_API_KEY_${STAGE_UPPER}" OPENAI_API_KEY
copy_value "OPENAI_API_BASE_URL_${STAGE_UPPER}" "OPENAI_API_BASE_URL_${STAGE_UPPER}" OPENAI_API_BASE_URL
copy_value "MEETING_RECORDING_TRANSCRIPTION_MODEL_${STAGE_UPPER}" "MEETING_RECORDING_TRANSCRIPTION_MODEL_${STAGE_UPPER}" MEETING_RECORDING_TRANSCRIPTION_MODEL
copy_value "MEETING_RECORDING_MAX_UPLOAD_BYTES_${STAGE_UPPER}" "MEETING_RECORDING_MAX_UPLOAD_BYTES_${STAGE_UPPER}" MEETING_RECORDING_MAX_UPLOAD_BYTES
copy_value "MEETING_RECORDING_CONTEXT_CHAR_LIMIT_${STAGE_UPPER}" "MEETING_RECORDING_CONTEXT_CHAR_LIMIT_${STAGE_UPPER}" MEETING_RECORDING_CONTEXT_CHAR_LIMIT
copy_value "G2B_API_KEY_${STAGE_UPPER}" "G2B_API_KEY_${STAGE_UPPER}" G2B_API_KEY
copy_value "PROCUREMENT_SMOKE_URL_OR_NUMBER_${STAGE_UPPER}" "PROCUREMENT_SMOKE_URL_OR_NUMBER_${STAGE_UPPER}" PROCUREMENT_SMOKE_URL_OR_NUMBER SMOKE_PROCUREMENT_URL_OR_NUMBER
copy_value "PROCUREMENT_SMOKE_TENANT_ID_${STAGE_UPPER}" "PROCUREMENT_SMOKE_TENANT_ID_${STAGE_UPPER}" PROCUREMENT_SMOKE_TENANT_ID SMOKE_TENANT_ID
copy_value "PROCUREMENT_SMOKE_USERNAME_${STAGE_UPPER}" "PROCUREMENT_SMOKE_USERNAME_${STAGE_UPPER}" PROCUREMENT_SMOKE_USERNAME
copy_value "PROCUREMENT_SMOKE_PASSWORD_${STAGE_UPPER}" "PROCUREMENT_SMOKE_PASSWORD_${STAGE_UPPER}" PROCUREMENT_SMOKE_PASSWORD
copy_value "VOICE_BRIEF_API_BASE_URL_${STAGE_UPPER}" "VOICE_BRIEF_API_BASE_URL_${STAGE_UPPER}" VOICE_BRIEF_API_BASE_URL
copy_value "VOICE_BRIEF_API_BEARER_TOKEN_${STAGE_UPPER}" "VOICE_BRIEF_API_BEARER_TOKEN_${STAGE_UPPER}" VOICE_BRIEF_API_BEARER_TOKEN
copy_value "VOICE_BRIEF_TIMEOUT_SECONDS_${STAGE_UPPER}" "VOICE_BRIEF_TIMEOUT_SECONDS_${STAGE_UPPER}" VOICE_BRIEF_TIMEOUT_SECONDS
copy_value "VOICE_BRIEF_SMOKE_RECORDING_ID_${STAGE_UPPER}" "VOICE_BRIEF_SMOKE_RECORDING_ID_${STAGE_UPPER}" VOICE_BRIEF_SMOKE_RECORDING_ID
copy_value "VOICE_BRIEF_SMOKE_REVISION_ID_${STAGE_UPPER}" "VOICE_BRIEF_SMOKE_REVISION_ID_${STAGE_UPPER}" VOICE_BRIEF_SMOKE_REVISION_ID
copy_value "VOICE_BRIEF_SMOKE_TENANT_ID_${STAGE_UPPER}" "VOICE_BRIEF_SMOKE_TENANT_ID_${STAGE_UPPER}" VOICE_BRIEF_SMOKE_TENANT_ID
copy_value "VOICE_BRIEF_SMOKE_USERNAME_${STAGE_UPPER}" "VOICE_BRIEF_SMOKE_USERNAME_${STAGE_UPPER}" VOICE_BRIEF_SMOKE_USERNAME
copy_value "VOICE_BRIEF_SMOKE_PASSWORD_${STAGE_UPPER}" "VOICE_BRIEF_SMOKE_PASSWORD_${STAGE_UPPER}" VOICE_BRIEF_SMOKE_PASSWORD

echo "Generated GitHub Actions env scaffold:"
echo "  stage:  $STAGE"
echo "  source: $SOURCE_FILE"
echo "  output: $OUTPUT_FILE"
echo

if [[ ${#UPDATED[@]} -gt 0 ]]; then
  echo "Populated entries:"
  for name in "${UPDATED[@]}"; do
    echo "  - $name"
  done
fi

if [[ ${#PRESERVED[@]} -gt 0 ]]; then
  echo
  echo "Already present in output:"
  for name in "${PRESERVED[@]}"; do
    echo "  - $name"
  done
fi

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  echo
  echo "Skipped local-only values:"
  for name in "${SKIPPED[@]}"; do
    echo "  - $name"
  done
fi

echo
echo "Still empty after import:"
for name in "${UNRESOLVED[@]}"; do
  echo "  - $name"
done
