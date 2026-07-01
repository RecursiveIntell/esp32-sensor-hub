// Generated from contracts/sensor_policy_s3_local_language_v1.json.
// Keep this file in sync with ri-esp-policy / ri-esp-local-language.
#pragma once

#define RI_SENSOR_POLICY_CONTRACT_SCHEMA "ri_sensor_policy_s3_contract_v1"
#define RI_LOCAL_LANGUAGE_MODEL "esp32s3_h320_p15"
#define RI_S3_LANGUAGE_RECEIPT_SCHEMA "ri_esp32s3_local_language_v1"
#define RI_SENSOR_POLICY_INTEGRATION_SCHEMA "ri_sensor_policy_to_s3_language_integration_v1"

static constexpr unsigned long RI_POLICY_STALE_AFTER_MS = 120000UL;
static constexpr float RI_POLICY_HOT_F = 82.0f;
static constexpr float RI_POLICY_COLD_F = 60.0f;
static constexpr float RI_POLICY_HUMID_PCT = 65.0f;
static constexpr float RI_POLICY_DRY_PCT = 25.0f;

#define RI_PROMPT_MISSING_SENSOR "missing sensor. action is "
#define RI_PROMPT_STALE_DATA "stale data. action is "
#define RI_PROMPT_HIGH_HEAT_HUMIDITY "high heat and humidity. action is "
#define RI_PROMPT_HOT_ROOM "hot room. action is "
#define RI_PROMPT_HUMID_ROOM "humid room. action is "
#define RI_PROMPT_NORMAL_ROOM "normal room. action is "
#define RI_PROMPT_SAFE_ACTION "safe action is "
#define RI_PROMPT_LOCAL_FIRST_MEANS "local first means "

#define RI_OUTPUT_MISSING_SENSOR "no claim."
#define RI_OUTPUT_STALE_DATA "wait for fresh data."
#define RI_OUTPUT_HIGH_HEAT_HUMIDITY "escalate."
#define RI_OUTPUT_HOT_ROOM "check airflow."
#define RI_OUTPUT_HUMID_ROOM "ventilate."
#define RI_OUTPUT_NORMAL_ROOM "log receipt."
#define RI_OUTPUT_SAFE_ACTION "no claim without evidence."
#define RI_OUTPUT_LOCAL_FIRST_MEANS "decide before cloud."
