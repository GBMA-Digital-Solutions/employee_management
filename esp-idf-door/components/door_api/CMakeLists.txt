idf_component_register(
    SRCS "door_api.c"
    INCLUDE_DIRS "include"
    REQUIRES door_wifi esp_http_client esp_hw_support mbedtls
)
