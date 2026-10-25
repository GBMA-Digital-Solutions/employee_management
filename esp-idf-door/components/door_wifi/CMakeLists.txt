idf_component_register(
    SRCS "door_wifi.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_common esp_event esp_netif esp_wifi lwip nvs_flash
)
