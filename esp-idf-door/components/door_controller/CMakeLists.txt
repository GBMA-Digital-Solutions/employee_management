idf_component_register(
    SRCS "door_controller.c"
    INCLUDE_DIRS "include"
    REQUIRES door_api door_wifi maglock
)
