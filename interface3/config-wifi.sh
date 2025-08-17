#!/bin/sh

set -e

echo "Configure your interface3 3270 adapter's WiFi connection"
echo

/bin/echo -n "WiFi network name"
if [ "$wifi_name" != "" ]
then
    /bin/echo -n " [$wifi_name]"
fi
/bin/echo -n ": "
read wifi_name_entered
if [ -z "$wifi_name_entered" ]
then
    if [ -z "$wifi_name" ]
    then
        exit 1
    fi
else
    wifi_name="$wifi_name_entered"
fi
/bin/echo -n "WiFi password: "
stty -echo
read wifi_password

old_config=$(mktemp)
new_config=$(mktemp)
trap "rm -f $old_config $new_config" 0
if mpremote ls | grep -q ' config.json'
then
    mpremote cp --no-verbose :config.json $old_config
else
    echo "{}" > $old_config
fi
jq ".wifi.ssid=\"$wifi_name\" | .wifi.password=\"$wifi_password\"" < $old_config > $new_config
mpremote cp --no-verbose $new_config :config.json
echo "Device has been configured to join network $wifi_name"
echo
mpremote reset
sleep 1
mpremote repl
