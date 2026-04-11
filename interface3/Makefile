# Build the firmware/ tree for all four Pico variants and copy the
# resulting UF2 images out into this directory.

FIRMWARE_DIR := firmware
BOARDS       := pico pico_w pico2 pico2_w
UF2S         := $(addprefix coax_interface-,$(addsuffix .uf2,$(BOARDS)))

# Use the pico-sdk vendored under firmware/ unless the caller already
# has PICO_SDK_PATH set.
export PICO_SDK_PATH ?= $(abspath $(FIRMWARE_DIR)/pico-sdk)

.PHONY: all $(BOARDS) clean distclean

all: $(UF2S)

# Per-board build rule. Configures a dedicated build directory under
# firmware/build-<board>/, runs the build, then copies the UF2 here.
define BOARD_template
coax_interface-$(1).uf2: | $(FIRMWARE_DIR)/build-$(1)/build.ninja
	cmake --build $(FIRMWARE_DIR)/build-$(1)
	cp $(FIRMWARE_DIR)/build-$(1)/coax_interface.uf2 $$@

$(FIRMWARE_DIR)/build-$(1)/build.ninja:
	cmake -S $(FIRMWARE_DIR) -B $(FIRMWARE_DIR)/build-$(1) -G Ninja -DPICO_BOARD=$(1)

$(1): coax_interface-$(1).uf2
endef

$(foreach board,$(BOARDS),$(eval $(call BOARD_template,$(board))))

clean:
	rm -f $(UF2S)
	for b in $(BOARDS); do \
	  if [ -d $(FIRMWARE_DIR)/build-$$b ]; then \
	    cmake --build $(FIRMWARE_DIR)/build-$$b --target clean; \
	  fi; \
	done

distclean:
	rm -f $(UF2S)
	rm -rf $(addprefix $(FIRMWARE_DIR)/build-,$(BOARDS))
