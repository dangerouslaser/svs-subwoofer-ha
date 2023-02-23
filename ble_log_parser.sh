#!/bin/bash
tshark -Y btatt -O hci_h4,btatt -r $1 | awk -F'[: ]+' '$1~/Frame/ { printf "\n%s ", $2}; $2~/Direct/ {printf "%s ", $3}; $2~/Value/ {printf "%s", $3}'

