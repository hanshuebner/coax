#!/bin/sh

set -e

if [ $(uname) = Darwin ]
then
    wifi_name=$(/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I | perl -ne '/^\s*SSID: (.*)\n/ && print $1')
    echo "You will be asked for an administrator account name and password so that your WiFi password can be retrieved."
    echo "Cancel to enter password manually."
    wifi_password=$(security find-generic-password -ga "$wifi_name" 2>&1 | perl -ne '/^password: "(.*)"/ && print $1')
fi

if [ "$wifi_password" = "" ]
then
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
fi

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
mpremote reset
sleep 1
mpremote repl
