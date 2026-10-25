#pragma once

#include <stdbool.h>
#include "esp_err.h"

typedef void (*door_wifi_disconnected_cb_t)(void);

esp_err_t door_wifi_start(door_wifi_disconnected_cb_t disconnected_cb);
void door_wifi_wait_connected(void);
bool door_wifi_is_connected(void);
