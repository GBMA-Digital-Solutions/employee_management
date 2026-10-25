#pragma once

#include "esp_err.h"

esp_err_t maglock_init(void);
void maglock_lock(void);
void maglock_unlock(void);
