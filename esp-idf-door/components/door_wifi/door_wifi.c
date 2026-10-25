#include <string.h>
#include <time.h>

#include "door_wifi.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "door_wifi";
static EventGroupHandle_t wifi_events;
static door_wifi_disconnected_cb_t on_disconnected;

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = (wifi_event_sta_disconnected_t *)event_data;
        xEventGroupClearBits(wifi_events, WIFI_CONNECTED_BIT);
        if (on_disconnected) {
            on_disconnected();
        }
        esp_wifi_connect();
        /* The reason code is the difference between a wrong password (204 or
           15), a network out of range or on 5 GHz only (201), and a passing
           glitch, so log it rather than a bare "disconnected". */
        ESP_LOGW(TAG, "Disconnected from \"%s\", reason %d; reconnecting",
                 CONFIG_DOOR_WIFI_SSID, event->reason);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Connected, IP=" IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(wifi_events, WIFI_CONNECTED_BIT);
    }
}

static esp_err_t initialize_nvs(void)
{
    esp_err_t result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "Could not erase NVS");
        result = nvs_flash_init();
    }
    return result;
}

static void synchronize_clock(void)
{
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
    for (int attempt = 0; attempt < 40 && time(NULL) < 1700000000; ++attempt) {
        vTaskDelay(pdMS_TO_TICKS(250));
    }
    ESP_LOGI(TAG, "Clock synchronization %s", time(NULL) >= 1700000000 ? "ready" : "pending");
}

esp_err_t door_wifi_start(door_wifi_disconnected_cb_t disconnected_cb)
{
    on_disconnected = disconnected_cb;
    ESP_RETURN_ON_ERROR(initialize_nvs(), TAG, "NVS initialization failed");
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "Network stack initialization failed");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "Event loop creation failed");
    esp_netif_create_default_wifi_sta();

    wifi_events = xEventGroupCreate();
    if (!wifi_events) {
        return ESP_ERR_NO_MEM;
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "Wi-Fi initialization failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                    event_handler, NULL), TAG, "Wi-Fi handler failed");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                                    event_handler, NULL), TAG, "IP handler failed");

    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, CONFIG_DOOR_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_DOOR_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.threshold.authmode = strlen(CONFIG_DOOR_WIFI_PASSWORD)
        ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    config.sta.pmf_cfg.capable = true;

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "Station mode failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "Wi-Fi configuration failed");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "Wi-Fi start failed");
    /* Modem sleep would add hundreds of milliseconds to a poll, and an unlock
       command is only valid for a few seconds. */
    ESP_RETURN_ON_ERROR(esp_wifi_set_ps(WIFI_PS_NONE), TAG, "Could not disable Wi-Fi power save");
    ESP_LOGI(TAG, "Joining \"%s\"", CONFIG_DOOR_WIFI_SSID);
    door_wifi_wait_connected();
    synchronize_clock();
    return ESP_OK;
}

void door_wifi_wait_connected(void)
{
    xEventGroupWaitBits(wifi_events, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
}

bool door_wifi_is_connected(void)
{
    return wifi_events && (xEventGroupGetBits(wifi_events) & WIFI_CONNECTED_BIT);
}
