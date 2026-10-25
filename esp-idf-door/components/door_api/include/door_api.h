#pragma once

#include <stdbool.h>
#include <stdint.h>

#define DOOR_COMMAND_ID_CAPACITY 64

typedef struct {
    char id[DOOR_COMMAND_ID_CAPACITY];
    uint32_t duration_ms;
} door_command_t;

/* True when the server handed over an authorized unlock, filling `command`. */
bool door_api_poll(door_command_t *command);

/* Reports `state` ("executing", "completed" or "failed") for a command,
   retrying a few times because the server's record of the door depends on it. */
bool door_api_acknowledge(const char *command_id, const char *state, const char *error);

/* Drops the kept-alive connection, which cannot outlive a Wi-Fi session. */
void door_api_reset_connection(void);
