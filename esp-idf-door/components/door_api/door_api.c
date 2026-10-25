#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "door_api.h"
#include "door_wifi.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/md.h"

#define HTTP_RESPONSE_CAPACITY 2048
/* The server rejects a signature whose timestamp is outside its window, so a
   request is pointless until SNTP has replaced the 1970 boot clock. */
#define CLOCK_READY_EPOCH 1700000000
/* A dropped acknowledgement leaves the door recorded as locked while it is
   open, so retry it; a poll simply happens again on the next tick. */
#define ACK_ATTEMPTS 3
#define ACK_RETRY_DELAY_MS 300
/* An unreachable API fails on every poll. Log the first and then one in
   FAILURE_LOG_EVERY so the monitor stays readable. */
#define FAILURE_LOG_EVERY 25
#define DEFAULT_UNLOCK_MS 5000
#define MAX_UNLOCK_MS 30000

static const char *TAG = "door_api";

typedef struct {
    char data[HTTP_RESPONSE_CAPACITY];
    size_t length;
} http_response_t;

/* One connection serves every poll and acknowledgement. Rebuilding it per
   request would mean a fresh TLS handshake several times a second, which no
   ESP32 finishes inside the poll interval. */
static esp_http_client_handle_t client;
static http_response_t response;
static unsigned poll_failures;

static bool fits(int written, size_t capacity)
{
    return written >= 0 && (size_t)written < capacity;
}

static void bytes_to_hex(const unsigned char *input, size_t length, char *output)
{
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < length; ++i) {
        output[i * 2] = hex[input[i] >> 4];
        output[i * 2 + 1] = hex[input[i] & 0x0f];
    }
    output[length * 2] = 0;
}

static bool make_signature(const char *path, const char *timestamp,
                           const char *nonce, const char *body, char output[65])
{
    unsigned char body_digest[32], key[32], signature[32];
    char body_hash[65], canonical[512];
    const mbedtls_md_info_t *sha256 = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!sha256 ||
        mbedtls_md(sha256, (const unsigned char *)body, strlen(body), body_digest) != 0 ||
        mbedtls_md(sha256, (const unsigned char *)CONFIG_DOOR_DEVICE_SECRET,
                   strlen(CONFIG_DOOR_DEVICE_SECRET), key) != 0) {
        return false;
    }
    bytes_to_hex(body_digest, sizeof(body_digest), body_hash);
    if (!fits(snprintf(canonical, sizeof(canonical), "POST\n%s\n%s\n%s\n%s",
                       path, timestamp, nonce, body_hash), sizeof(canonical)) ||
        mbedtls_md_hmac(sha256, key, sizeof(key),
                        (const unsigned char *)canonical, strlen(canonical), signature) != 0) {
        return false;
    }
    bytes_to_hex(signature, sizeof(signature), output);
    return true;
}

static esp_err_t http_event_handler(esp_http_client_event_t *event)
{
    http_response_t *body = (http_response_t *)event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && body && event->data_len > 0) {
        size_t available = sizeof(body->data) - body->length - 1;
        size_t copy = (size_t)event->data_len < available ? (size_t)event->data_len : available;
        memcpy(body->data + body->length, event->data, copy);
        body->length += copy;
        body->data[body->length] = 0;
    }
    return ESP_OK;
}

static bool open_client(void)
{
    if (client) {
        return true;
    }
    esp_http_client_config_t config = {
        /* Every request replaces this with esp_http_client_set_url(). */
        .url = CONFIG_DOOR_API_BASE_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
        .user_data = &response,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 10000,
        .keep_alive_enable = true,
        .buffer_size = 1024,
    };
    client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "No memory for the HTTP client");
        return false;
    }
    esp_http_client_set_header(client, "Content-Type", "application/json");
    return true;
}

static void close_client(void)
{
    if (client) {
        esp_http_client_cleanup(client);
        client = NULL;
    }
}

static int signed_post(const char *path, const char *body)
{
    response.length = 0;
    response.data[0] = 0;
    if (!door_wifi_is_connected() || time(NULL) < CLOCK_READY_EPOCH) {
        return -1;
    }

    char timestamp[24], nonce[24], signature[65], url[384];
    snprintf(timestamp, sizeof(timestamp), "%" PRId64, (int64_t)time(NULL));
    snprintf(nonce, sizeof(nonce), "%08" PRIx32 "%08" PRIx32, esp_random(), esp_random());
    if (!make_signature(path, timestamp, nonce, body, signature)) {
        ESP_LOGE(TAG, "Could not sign the request for %s", path);
        return -1;
    }
    if (!fits(snprintf(url, sizeof(url), "%s%s", CONFIG_DOOR_API_BASE_URL, path), sizeof(url))) {
        ESP_LOGE(TAG, "API base URL and path are longer than %u bytes", (unsigned)sizeof(url));
        return -1;
    }
    if (!open_client()) {
        return -1;
    }

    esp_http_client_set_url(client, url);
    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "X-Door-Timestamp", timestamp);
    esp_http_client_set_header(client, "X-Door-Nonce", nonce);
    esp_http_client_set_header(client, "X-Door-Signature", signature);
    esp_http_client_set_post_field(client, body, strlen(body));

    esp_err_t error = esp_http_client_perform(client);
    if (error != ESP_OK) {
        /* The connection is in an unknown state; the next call builds a new one. */
        ESP_LOGD(TAG, "POST %s failed: %s", path, esp_err_to_name(error));
        close_client();
        return -1;
    }
    return esp_http_client_get_status_code(client);
}

static bool json_string_value(const char *json, const char *key, char *output, size_t capacity)
{
    const char *position = strstr(json, key);
    position = position ? strchr(position + strlen(key), ':') : NULL;
    position = position ? strchr(position, '"') : NULL;
    if (!position) {
        return false;
    }
    const char *end = strchr(++position, '"');
    size_t length = end ? (size_t)(end - position) : 0;
    if (!end || length == 0 || length >= capacity) {
        return false;
    }
    memcpy(output, position, length);
    output[length] = 0;
    return true;
}

void door_api_reset_connection(void)
{
    close_client();
}

bool door_api_poll(door_command_t *command_result)
{
    char path[192];
    if (!fits(snprintf(path, sizeof(path), "/api/door-devices/%s/poll/", CONFIG_DOOR_DEVICE_ID),
              sizeof(path))) {
        ESP_LOGE(TAG, "Device ID is too long for a poll URL");
        return false;
    }
    int status = signed_post(path, "{}");
    if (status != 200) {
        if (poll_failures++ % FAILURE_LOG_EVERY == 0) {
            ESP_LOGW(TAG, "Poll -> HTTP %d %.200s (failure %u)", status, response.data, poll_failures);
        }
        return false;
    }
    if (poll_failures) {
        ESP_LOGI(TAG, "Reaching the API again after %u failed polls", poll_failures);
        poll_failures = 0;
    }

    const char *command = strstr(response.data, "\"command\"");
    const char *value = command ? strchr(command, ':') : NULL;
    if (!value) {
        return false;
    }
    do {
        ++value;
    } while (*value == ' ' || *value == '\t');
    if (strncmp(value, "null", 4) == 0) {
        return false;
    }

    char action[16];
    if (!json_string_value(command, "\"id\"", command_result->id, sizeof(command_result->id)) ||
        !json_string_value(command, "\"action\"", action, sizeof(action)) ||
        strcmp(action, "unlock") != 0) {
        ESP_LOGW(TAG, "Ignoring a malformed or unsupported command: %.200s", response.data);
        return false;
    }
    const char *duration = strstr(command, "\"duration_ms\"");
    duration = duration ? strchr(duration, ':') : NULL;
    command_result->duration_ms = duration ? (uint32_t)strtoul(duration + 1, NULL, 10) : DEFAULT_UNLOCK_MS;
    if (command_result->duration_ms == 0 || command_result->duration_ms > MAX_UNLOCK_MS) {
        command_result->duration_ms = DEFAULT_UNLOCK_MS;
    }
    ESP_LOGI(TAG, "Unlock command %s for %" PRIu32 " ms", command_result->id, command_result->duration_ms);
    return true;
}

bool door_api_acknowledge(const char *command_id, const char *state, const char *error)
{
    char path[256], body[160];
    if (!fits(snprintf(path, sizeof(path), "/api/door-devices/%s/commands/%s/ack/",
                       CONFIG_DOOR_DEVICE_ID, command_id), sizeof(path))) {
        ESP_LOGE(TAG, "Device ID and command ID are too long for an ack URL");
        return false;
    }
    if (error) {
        snprintf(body, sizeof(body), "{\"status\":\"%s\",\"error\":\"%s\"}", state, error);
    } else {
        snprintf(body, sizeof(body), "{\"status\":\"%s\"}", state);
    }
    for (int attempt = 1; attempt <= ACK_ATTEMPTS; ++attempt) {
        int status = signed_post(path, body);
        if (status == 200) {
            ESP_LOGI(TAG, "ACK %s accepted", state);
            return true;
        }
        /* 409 and 410 are final answers about this command. Only a transport
           or server failure is worth sending again. */
        if (status == 409 || status == 410) {
            ESP_LOGW(TAG, "ACK %s refused: HTTP %d %.200s", state, status, response.data);
            return false;
        }
        ESP_LOGW(TAG, "ACK %s attempt %d of %d -> HTTP %d %.200s",
                 state, attempt, ACK_ATTEMPTS, status, response.data);
        if (attempt < ACK_ATTEMPTS) {
            vTaskDelay(pdMS_TO_TICKS(ACK_RETRY_DELAY_MS));
        }
    }
    return false;
}
