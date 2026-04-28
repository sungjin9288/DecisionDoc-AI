#!/bin/bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
STAGE=""
ENV_FILE=""
ENABLE_VOICE_BRIEF=0
ENABLE_VOICE_BRIEF_SMOKE=0
ENABLE_PROCUREMENT_SMOKE=0
ENABLE_DOCKER_DEPLOY=0
NON_EMPTY_TENANT=0

usage() {
  cat <<EOF
Usage: ./$SCRIPT_NAME --stage <dev|prod> [options]

Options:
  --env-file <path>         Load values from a dotenv-formatted file
  --voice-brief             Require Voice Brief runtime settings for the stage
  --voice-brief-smoke       Require Voice Brief smoke settings for the stage
  --procurement-smoke       Require procurement smoke settings for the stage
  --docker-deploy           Require Docker server deploy secrets for the stage
  --non-empty-tenant        Require smoke username/password for the stage
  -h, --help                Show this help message

Examples:
  bash scripts/$SCRIPT_NAME --stage dev --env-file .github-actions.env
  bash scripts/$SCRIPT_NAME --stage dev --env-file .github-actions.env --docker-deploy --procurement-smoke --voice-brief --voice-brief-smoke
  bash scripts/$SCRIPT_NAME --stage prod --env-file .github-actions.env --docker-deploy --procurement-smoke --voice-brief --voice-brief-smoke --non-empty-tenant
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      STAGE=${2:-}
      shift 2
      ;;
    --env-file)
      ENV_FILE=${2:-}
      shift 2
      ;;
    --voice-brief)
      ENABLE_VOICE_BRIEF=1
      shift
      ;;
    --voice-brief-smoke)
      ENABLE_VOICE_BRIEF=1
      ENABLE_VOICE_BRIEF_SMOKE=1
      shift
      ;;
    --procurement-smoke)
      ENABLE_PROCUREMENT_SMOKE=1
      shift
      ;;
    --docker-deploy)
      ENABLE_DOCKER_DEPLOY=1
      shift
      ;;
    --non-empty-tenant)
      NON_EMPTY_TENANT=1
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

if [[ -n "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

STAGE_UPPER=$(printf '%s' "$STAGE" | tr '[:lower:]' '[:upper:]')
if [[ "$STAGE" == "dev" ]]; then
  DEPLOY_SECRET_PREFIX="STAGING"
else
  DEPLOY_SECRET_PREFIX="PROD"
fi

required=(
  AWS_REGION
  DECISIONDOC_API_KEY
  DECISIONDOC_OPS_KEY
  "AWS_ROLE_ARN_${STAGE_UPPER}"
  "DECISIONDOC_S3_BUCKET_${STAGE_UPPER}"
  "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_${STAGE_UPPER}"
)

optional=()
invalid=()

optional+=("DECISIONDOC_API_KEYS")
optional+=("OPENAI_API_KEY_${STAGE_UPPER}")
optional+=("OPENAI_API_BASE_URL_${STAGE_UPPER}")
optional+=("MEETING_RECORDING_TRANSCRIPTION_MODEL_${STAGE_UPPER}")
optional+=("MEETING_RECORDING_MAX_UPLOAD_BYTES_${STAGE_UPPER}")
optional+=("MEETING_RECORDING_CONTEXT_CHAR_LIMIT_${STAGE_UPPER}")

is_local_only_url() {
  local value=$1
  [[ "$value" =~ ^https?://(localhost|127\.[0-9]+\.[0-9]+\.[0-9]+|0\.0\.0\.0)(:[0-9]+)?([/?#].*)?$ ]]
}

if [[ "$ENABLE_VOICE_BRIEF" -eq 1 ]]; then
  required+=("VOICE_BRIEF_API_BASE_URL_${STAGE_UPPER}")
  optional+=("VOICE_BRIEF_API_BEARER_TOKEN_${STAGE_UPPER}")
  optional+=("VOICE_BRIEF_TIMEOUT_SECONDS_${STAGE_UPPER}")
fi

optional+=("G2B_API_KEY_${STAGE_UPPER}")
optional+=("STATUSPAGE_PAGE_ID")
optional+=("STATUSPAGE_API_KEY")

deploy_secret_names=(
  "${DEPLOY_SECRET_PREFIX}_HOST"
  "${DEPLOY_SECRET_PREFIX}_USER"
  "${DEPLOY_SECRET_PREFIX}_SSH_KEY"
)

if [[ "$ENABLE_DOCKER_DEPLOY" -eq 1 ]]; then
  required+=("${deploy_secret_names[@]}")
else
  optional+=("${deploy_secret_names[@]}")
fi

if [[ "$ENABLE_PROCUREMENT_SMOKE" -eq 1 ]]; then
  required+=("G2B_API_KEY_${STAGE_UPPER}")
  optional+=("PROCUREMENT_SMOKE_TENANT_ID_${STAGE_UPPER}")
  optional+=("PROCUREMENT_SMOKE_URL_OR_NUMBER_${STAGE_UPPER}")
  optional+=("PROCUREMENT_SMOKE_USERNAME_${STAGE_UPPER}")
  optional+=("PROCUREMENT_SMOKE_PASSWORD_${STAGE_UPPER}")
fi

if [[ "$ENABLE_VOICE_BRIEF_SMOKE" -eq 1 ]]; then
  required+=("VOICE_BRIEF_SMOKE_RECORDING_ID_${STAGE_UPPER}")
  optional+=("VOICE_BRIEF_SMOKE_REVISION_ID_${STAGE_UPPER}")
  optional+=("VOICE_BRIEF_SMOKE_TENANT_ID_${STAGE_UPPER}")
  if [[ "$NON_EMPTY_TENANT" -eq 1 ]]; then
    required+=("VOICE_BRIEF_SMOKE_USERNAME_${STAGE_UPPER}")
    required+=("VOICE_BRIEF_SMOKE_PASSWORD_${STAGE_UPPER}")
  else
    optional+=("VOICE_BRIEF_SMOKE_USERNAME_${STAGE_UPPER}")
    optional+=("VOICE_BRIEF_SMOKE_PASSWORD_${STAGE_UPPER}")
  fi
fi

missing=()

echo "Checking GitHub Actions config for stage=$STAGE"
if [[ -n "$ENV_FILE" ]]; then
  echo "Loaded values from: $ENV_FILE"
fi
echo

echo "Required entries:"
for name in "${required[@]}"; do
  value=${!name-}
  if [[ -n "$value" ]]; then
    echo "  OK     $name"
  else
    echo "  MISSING $name"
    missing+=("$name")
  fi
done

if [[ ${#optional[@]} -gt 0 ]]; then
  echo
  echo "Optional entries:"
  for name in "${optional[@]}"; do
    value=${!name-}
    if [[ -n "$value" ]]; then
      echo "  SET    $name"
    else
      echo "  EMPTY  $name"
    fi
  done
fi

if [[ "$ENABLE_VOICE_BRIEF" -eq 1 ]]; then
  voice_brief_base_url_name="VOICE_BRIEF_API_BASE_URL_${STAGE_UPPER}"
  voice_brief_base_url_value=${!voice_brief_base_url_name-}
  if [[ -n "$voice_brief_base_url_value" ]] && is_local_only_url "$voice_brief_base_url_value"; then
    echo
    echo "Invalid entries:"
    echo "  INVALID $voice_brief_base_url_name (loopback URLs do not work from GitHub-hosted runners)"
    invalid+=("$voice_brief_base_url_name")
  fi
fi

openai_base_url_name="OPENAI_API_BASE_URL_${STAGE_UPPER}"
openai_base_url_value=${!openai_base_url_name-}
if [[ -n "$openai_base_url_value" ]] && is_local_only_url "$openai_base_url_value"; then
  echo
  echo "Invalid entries:"
  echo "  INVALID $openai_base_url_name (loopback URLs do not work from Lambda runtime)"
  invalid+=("$openai_base_url_name")
fi

deploy_host_name="${DEPLOY_SECRET_PREFIX}_HOST"
deploy_user_name="${DEPLOY_SECRET_PREFIX}_USER"
deploy_key_name="${DEPLOY_SECRET_PREFIX}_SSH_KEY"
deploy_host_value=${!deploy_host_name-}
deploy_user_value=${!deploy_user_name-}
deploy_key_value=${!deploy_key_name-}
deploy_secret_count=0
[[ -n "$deploy_host_value" ]] && deploy_secret_count=$((deploy_secret_count + 1))
[[ -n "$deploy_user_value" ]] && deploy_secret_count=$((deploy_secret_count + 1))
[[ -n "$deploy_key_value" ]] && deploy_secret_count=$((deploy_secret_count + 1))
if [[ "$deploy_secret_count" -ne 0 && "$deploy_secret_count" -ne 3 ]]; then
  echo
  echo "Invalid entries:"
  echo "  INVALID ${DEPLOY_SECRET_PREFIX}_* (set ${deploy_host_name}, ${deploy_user_name}, and ${deploy_key_name} together)"
  invalid+=("${DEPLOY_SECRET_PREFIX}_*")
fi

echo
if [[ ${#missing[@]} -gt 0 || ${#invalid[@]} -gt 0 ]]; then
  if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Missing required entries (${#missing[@]}):"
  for name in "${missing[@]}"; do
    echo "  - $name"
  done
  fi
  if [[ ${#invalid[@]} -gt 0 ]]; then
    echo "Invalid entries (${#invalid[@]}):"
    for name in "${invalid[@]}"; do
      echo "  - $name"
    done
  fi
  exit 1
fi

echo "All required entries are present."
