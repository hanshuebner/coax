cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(coax_interface C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(coax_interface
    main.c
    coax.c
    slip.c
    command.c
    leds.c
    usb_descriptors.c
)

pico_generate_pio_header(coax_interface ${CMAKE_CURRENT_LIST_DIR}/coax.pio)

target_include_directories(coax_interface PRIVATE ${CMAKE_CURRENT_LIST_DIR})

target_link_libraries(coax_interface
    pico_stdlib
    hardware_pio
    hardware_dma
    tinyusb_device
    tinyusb_board
)

# Disable default USB and UART stdout — we use TinyUSB CDC directly
pico_enable_stdio_usb(coax_interface 0)
pico_enable_stdio_uart(coax_interface 0)

pico_add_extra_outputs(coax_interface)
