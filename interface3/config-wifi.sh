#!/bin/sh

set -e

# Function to prompt for input with optional default value
read_with_prompt() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_password="$4"

    /bin/echo -n "$prompt"
    if [ "$default" != "" ]
    then
        if [ "$is_password" = "true" ]
        then
            /bin/echo -n " [****]"
        else
            /bin/echo -n " [$default]"
        fi
    fi
    /bin/echo -n ": "

    if [ "$is_password" = "true" ]
    then
        stty -echo
        read input_value
        stty echo
        echo ""
    else
        read input_value
    fi

    if [ -z "$input_value" ]
    then
        if [ -z "$default" ]
        then
            echo "$prompt is required"
            exit 1
        else
            eval "$var_name=\"$default\""
        fi
    else
        eval "$var_name=\"$input_value\""
    fi
}

echo "Configure your interface3 3270 adapter's WiFi connection"
echo

# Retrieve existing config from device
old_config=$(mktemp)
new_config=$(mktemp)
trap "rm -f $old_config $new_config" 0

if mpremote ls | grep -q ' config.json'
then
    mpremote cp --no-verbose :config.json $old_config
    # Extract existing values as defaults
    wifi_name=$(jq -r '.wifi.ssid // empty' "$old_config" 2>/dev/null || echo "")
    wifi_password=$(jq -r '.wifi.password // empty' "$old_config" 2>/dev/null || echo "")
    connect_to=$(jq -r '.connect_to // empty' "$old_config" 2>/dev/null || echo "")
else
    echo "{}" > $old_config
    wifi_name=""
    wifi_password=""
    connect_to=""
fi

read_with_prompt "WiFi network name" "$wifi_name" "wifi_name"
read_with_prompt "WiFi password" "$wifi_password" "wifi_password" "true"
read_with_prompt "Connect to oec at host[:port]" "$connect_to" "connect_to"
jq --arg ssid "$wifi_name" --arg pw "$wifi_password" --arg ct "$connect_to" \
   '.wifi.ssid=$ssid
  | .wifi.password=$pw
  | if $ct != "" then .connect_to=$ct else del(.connect_to) end' \
  < "$old_config" > "$new_config"
mpremote cp --no-verbose $new_config :config.json
echo "Device has been configured to join network $wifi_name"
echo
mpremote reset
sleep 1
mpremote repl
