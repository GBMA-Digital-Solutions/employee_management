#include "door_controller.h"
#include "door_api.h"
#include "door_wifi.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "maglock.h"

/* An empty Kconfig string is a compile-time constant, so a runtime
   `strlen(CONFIG_...) == 0` guard here would let the optimizer prove the rest
   of this function unreachable and drop the controller task, the Wi-Fi stack
   and the HTTP client from the image. The result flashes and boots but can
   never open a door, so refuse to build instead. */
_Static_assert(sizeof(CONFIG_DOOR_WIFI_SSID) > 1,
               "Set the Wi-Fi SSID: idf.py menuconfig -> Employee Management Door");
_Static_assert(sizeof(CONFIG_DOOR_DEVICE_SECRET) > 1,
               "Set the enrolled device secret: idf.py menuconfig -> Employee Management Door");

/* The TLS handshake runs on this task, which needs more than the usual stack. */
#define CONTROLLER_STACK_BYTES 10240

static const char *TAG = "door_controller";

static volatile bool connection_stale;

static void on_wifi_disconnected(void)
{
    /* This runs on the Wi-Fi event task, so it only raises a flag: closing the
       HTTP client here could race the controller task inside a request. */
    connection_stale = true;
    maglock_lock();
}

static void controller_task(void *arg)
{
    door_command_t command;
    while (true) {
        door_wifi_wait_connected();
        if (connection_stale) {
            /* A kept-alive socket does not survive a new Wi-Fi session. */
            connection_stale = false;
            door_api_reset_connection();
        }
        if (door_api_poll(&command)) {
            maglock_unlock();
            door_api_acknowledge(command.id, "executing", NULL);

            /* Relocking is local and unconditional, even if Wi-Fi disappears. */
            vTaskDelay(pdMS_TO_TICKS(command.duration_ms));
            maglock_lock();
            door_api_acknowledge(command.id, "completed", NULL);
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_DOOR_POLL_INTERVAL_MS));
    }
}

void door_controller_start(void)
{
    ESP_LOGI(TAG, "Door device %s -> %s", CONFIG_DOOR_DEVICE_ID, CONFIG_DOOR_API_BASE_URL);
    ESP_LOGI(TAG, "Relay GPIO %d unlocks %s, status LED GPIO %d, polling every %d ms",
             CONFIG_DOOR_RELAY_GPIO, CONFIG_DOOR_RELAY_ACTIVE_LOW ? "low" : "high",
             CONFIG_DOOR_STATUS_LED_GPIO, CONFIG_DOOR_POLL_INTERVAL_MS);
    ESP_ERROR_CHECK(maglock_init());
    ESP_ERROR_CHECK(door_wifi_start(on_wifi_disconnected));
    xTaskCreate(controller_task, "door_controller", CONTROLLER_STACK_BYTES, NULL, 5, NULL);
}
