#!/bin/bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
STAGE=""
ENV_FILE=""
REPO=""
ENVIRONMENT_SCOPE=""
ENABLE_VOICE_BRIEF=0
ENABLE_VOICE_BRIEF_SMOKE=0
ENABLE_PROCUREMENT_SMOKE=0
NON_EMPTY_TENANT=0
ENSURE_ENVIRONMENT=0
DRY_RUN=0

usage() {
  cat <<EOF
Usage: ./$SCRIPT_NAME --stage <dev|prod> --env-file <path> [options]

Options:
  --repo <owner/repo>       Target repository. Defaults to the current git remote.
  --environment <name>      Store secrets/variables at GitHub environment scope instead of repo scope
  --ensure-environment      Create the target GitHub environment first when --environment is used
  --voice-brief             Apply Voice Brief runtime settings for the stage
  --voice-brief-smoke       Apply Voice Brief smoke settings for the stage
  --procurement-smoke       Apply procurement smoke settings for the stage
  --non-empty-tenant        Require/apply smoke username/password for the stage
  --dry-run                 Print what would be applied without calling GitHub
  -h, --help                Show this help message

Examples:
  bash scripts/$SCRIPT_NAME --stage dev --env-file .github-actions.env --procurement-smoke --voice-brief --voice-brief-smoke --dry-run
  bash scripts/$SCRIPT_NAME --stage dev --env-file .github-actions.env --procurement-smoke --voice-brief --voice-brief-smoke
  bash scripts/$SCRIPT_NAME --stage dev --env-file .github-actions.env --environment dev --ensure-environment --procurement-smoke --voice-brief --voice-brief-smoke
  bash scripts/$SCRIPT_NAME --stage prod --env-file .github-actions.env --procurement-smoke --voice-brief --voice-brief-smoke --non-empty-tenant
EOF
}

infer_repo_from_git() {
  local remote
  remote=$(git remote get-url origin 2>/dev/null || true)
  if [[ -z "$remote" ]]; then
    return 1
  fi
  printf '%s\n' "$remote" | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##'
}

has_value() {
  local name=$1
  [[ -n "${!name-}" ]]
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
    --repo)
      REPO=${2:-}
      shift 2
      ;;
    --environment)
      ENVIRONMENT_SCOPE=${2:-}
      shift 2
      ;;
    --ensure-environment)
      ENSURE_ENVIRONMENT=1
      shift
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
    --non-empty-tenant)
      NON_EMPTY_TENANT=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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

if [[ -z "$ENV_FILE" ]]; then
  echo "ERROR: --env-file is required" >&2
  usage >&2
  exit 1
fi

if [[ -z "$REPO" ]]; then
  REPO=$(infer_repo_from_git || true)
fi

if [[ -z "$REPO" ]]; then
  echo "ERROR: could not infer GitHub repository. Use --repo owner/repo." >&2
  exit 1
fi

if [[ "$ENSURE_ENVIRONMENT" -eq 1 && -z "$ENVIRONMENT_SCOPE" ]]; then
  echo "ERROR: --ensure-environment requires --environment <name>" >&2
  exit 1
fi

check_args=(--stage "$STAGE" --env-file "$ENV_FILE")
if [[ "$ENABLE_VOICE_BRIEF" -eq 1 ]]; then
  check_args+=(--voice-brief)
fi
if [[ "$ENABLE_VOICE_BRIEF_SMOKE" -eq 1 ]]; then
  check_args+=(--voice-brief-smoke)
fi
if [[ "$ENABLE_PROCUREMENT_SMOKE" -eq 1 ]]; then
  check_args+=(--procurement-smoke)
fi
if [[ "$NON_EMPTY_TENANT" -eq 1 ]]; then
  check_args+=(--non-empty-tenant)
fi

bash "$SCRIPT_DIR/check-github-actions-config.sh" "${check_args[@]}"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

STAGE_UPPER=$(printf '%s' "$STAGE" | tr '[:lower:]' '[:upper:]')

secrets=(
  AWS_REGION
  DECISIONDOC_API_KEY
  DECISIONDOC_OPS_KEY
  "AWS_ROLE_ARN_${STAGE_UPPER}"
  "DECISIONDOC_S3_BUCKET_${STAGE_UPPER}"
)

variables=()
procurement_flag_name="DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_${STAGE_UPPER}"
openai_api_key_name="OPENAI_API_KEY_${STAGE_UPPER}"
openai_api_base_url_name="OPENAI_API_BASE_URL_${STAGE_UPPER}"
meeting_recording_model_name="MEETING_RECORDING_TRANSCRIPTION_MODEL_${STAGE_UPPER}"
meeting_recording_max_upload_name="MEETING_RECORDING_MAX_UPLOAD_BYTES_${STAGE_UPPER}"
meeting_recording_context_limit_name="MEETING_RECORDING_CONTEXT_CHAR_LIMIT_${STAGE_UPPER}"
g2b_api_key_name="G2B_API_KEY_${STAGE_UPPER}"
voice_brief_bearer_name="VOICE_BRIEF_API_BEARER_TOKEN_${STAGE_UPPER}"
voice_brief_timeout_name="VOICE_BRIEF_TIMEOUT_SECONDS_${STAGE_UPPER}"
voice_brief_smoke_revision_name="VOICE_BRIEF_SMOKE_REVISION_ID_${STAGE_UPPER}"
voice_brief_smoke_tenant_name="VOICE_BRIEF_SMOKE_TENANT_ID_${STAGE_UPPER}"
voice_brief_smoke_username_name="VOICE_BRIEF_SMOKE_USERNAME_${STAGE_UPPER}"
voice_brief_smoke_password_name="VOICE_BRIEF_SMOKE_PASSWORD_${STAGE_UPPER}"
procurement_smoke_url_name="PROCUREMENT_SMOKE_URL_OR_NUMBER_${STAGE_UPPER}"
procurement_smoke_tenant_name="PROCUREMENT_SMOKE_TENANT_ID_${STAGE_UPPER}"
procurement_smoke_username_name="PROCUREMENT_SMOKE_USERNAME_${STAGE_UPPER}"
procurement_smoke_password_name="PROCUREMENT_SMOKE_PASSWORD_${STAGE_UPPER}"

variables+=("$procurement_flag_name")

if has_value "DECISIONDOC_API_KEYS"; then
  secrets+=("DECISIONDOC_API_KEYS")
fi

if has_value "$openai_api_key_name"; then
  secrets+=("$openai_api_key_name")
fi
if has_value "$openai_api_base_url_name"; then
  variables+=("$openai_api_base_url_name")
fi
if has_value "$meeting_recording_model_name"; then
  variables+=("$meeting_recording_model_name")
fi
if has_value "$meeting_recording_max_upload_name"; then
  variables+=("$meeting_recording_max_upload_name")
fi
if has_value "$meeting_recording_context_limit_name"; then
  variables+=("$meeting_recording_context_limit_name")
fi

if has_value "$g2b_api_key_name"; then
  secrets+=("$g2b_api_key_name")
fi

if has_value "STATUSPAGE_PAGE_ID"; then
  secrets+=("STATUSPAGE_PAGE_ID")
fi

if has_value "STATUSPAGE_API_KEY"; then
  secrets+=("STATUSPAGE_API_KEY")
fi

if [[ "$ENABLE_VOICE_BRIEF" -eq 1 ]]; then
  secrets+=("VOICE_BRIEF_API_BASE_URL_${STAGE_UPPER}")
  variables+=("$voice_brief_timeout_name")
fi

if has_value "$voice_brief_bearer_name"; then
  secrets+=("$voice_brief_bearer_name")
fi

if [[ "$ENABLE_VOICE_BRIEF_SMOKE" -eq 1 ]]; then
  variables+=("VOICE_BRIEF_SMOKE_RECORDING_ID_${STAGE_UPPER}")
  if has_value "$voice_brief_smoke_revision_name"; then
    variables+=("$voice_brief_smoke_revision_name")
  fi
  if has_value "$voice_brief_smoke_tenant_name"; then
    variables+=("$voice_brief_smoke_tenant_name")
  fi
  if [[ "$NON_EMPTY_TENANT" -eq 1 ]] || has_value "$voice_brief_smoke_username_name" || has_value "$voice_brief_smoke_password_name"; then
    secrets+=("$voice_brief_smoke_username_name")
    secrets+=("$voice_brief_smoke_password_name")
  fi
fi

if [[ "$ENABLE_PROCUREMENT_SMOKE" -eq 1 ]]; then
  variables+=("$procurement_smoke_url_name")
  if has_value "$procurement_smoke_tenant_name"; then
    variables+=("$procurement_smoke_tenant_name")
  fi
  if has_value "$procurement_smoke_username_name" || has_value "$procurement_smoke_password_name"; then
    secrets+=("$procurement_smoke_username_name")
    secrets+=("$procurement_smoke_password_name")
  fi
fi

secret_scope_args=(-R "$REPO")
variable_scope_args=(-R "$REPO")
if [[ -n "$ENVIRONMENT_SCOPE" ]]; then
  secret_scope_args+=(--env "$ENVIRONMENT_SCOPE")
  variable_scope_args+=(--env "$ENVIRONMENT_SCOPE")
fi

echo "Applying GitHub Actions config to $REPO"
if [[ -n "$ENVIRONMENT_SCOPE" ]]; then
  echo "Scope: environment=$ENVIRONMENT_SCOPE"
  if [[ "$ENSURE_ENVIRONMENT" -eq 1 ]]; then
    echo "Environment bootstrap: enabled"
  fi
else
  echo "Scope: repository"
fi
echo "Stage: $STAGE"
echo

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run:"
  if [[ "$ENSURE_ENVIRONMENT" -eq 1 ]]; then
    echo "  environment $ENVIRONMENT_SCOPE"
  fi
  for name in "${secrets[@]}"; do
    echo "  secret   $name"
  done
  for name in "${variables[@]}"; do
    echo "  variable $name"
  done
  exit 0
fi

gh auth status >/dev/null

if [[ -n "$ENVIRONMENT_SCOPE" && "$ENSURE_ENVIRONMENT" -eq 1 ]]; then
  gh api --method PUT "repos/$REPO/environments/$ENVIRONMENT_SCOPE" >/dev/null
  echo "Ensured environment: $ENVIRONMENT_SCOPE"
fi

for name in "${secrets[@]}"; do
  value=${!name}
  gh secret set "$name" "${secret_scope_args[@]}" --body "$value"
  echo "Applied secret: $name"
done

for name in "${variables[@]}"; do
  value=${!name}
  gh variable set "$name" "${variable_scope_args[@]}" --body "$value"
  echo "Applied variable: $name"
done

echo
echo "GitHub Actions configuration applied successfully."
