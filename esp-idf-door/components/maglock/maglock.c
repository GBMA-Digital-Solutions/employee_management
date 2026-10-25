#include <stdbool.h>

#include "maglock.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "maglock";

#define STATUS_LED_ENABLED (CONFIG_DOOR_STATUS_LED_GPIO >= 0)

static void set_locked(bool locked)
{
    int unlock_level = CONFIG_DOOR_RELAY_ACTIVE_LOW ? 0 : 1;
    gpio_set_level(CONFIG_DOOR_RELAY_GPIO, locked ? !unlock_level : unlock_level);
#if STATUS_LED_ENABLED
    gpio_set_level(CONFIG_DOOR_STATUS_LED_GPIO, locked ? 0 : 1);
#endif
    ESP_LOGI(TAG, "%s", locked ? "LOCKED" : "UNLOCKED");
}

esp_err_t maglock_init(void)
{
    gpio_config_t outputs = {
        .pin_bit_mask = 1ULL << CONFIG_DOOR_RELAY_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
#if STATUS_LED_ENABLED
    outputs.pin_bit_mask |= 1ULL << CONFIG_DOOR_STATUS_LED_GPIO;
#endif
    esp_err_t result = gpio_config(&outputs);
    if (result == ESP_OK) {
        /* Hold the locked level before anything can ask for an unlock. */
        maglock_lock();
    }
    return result;
}

void maglock_lock(void)
{
    set_locked(true);
}

void maglock_unlock(void)
{
    set_locked(false);
}
