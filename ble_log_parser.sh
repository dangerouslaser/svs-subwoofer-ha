#!/bin/bash

tshark -Y "btatt and btatt.handle==0x0011" -O hci_h4,btatt -r $1 | awk -F'[: ]+' '$1~/Frame/ { printf "\n%s ", $2}; $2~/Direct/ {printf "%s ", $3}; $2~/Value/ {printf "%s", $3}' > traffic

#reverse traffic
tac traffic > traffic_reversed
rm -rf traffic

#join fragments
fragment_join=""
while IFS="" read -r p || [ -n "$p" ];
do
	current_frame=$(echo "$p" | cut -d ' ' -f 3)
	current_frame_start=$(echo $current_frame | cut -c 1,2)
	if [ "$current_frame_start" != "aa" ]; then
		fragment_join="$current_frame$fragment_join"
	else
		full_frame="$current_frame$fragment_join"
		decod=$(./pySVS.py -d "$full_frame")
		echo "$p$fragment_join $decod" >> traffic_reversed_decoded
		echo "" >> traffic_reversed_decoded
		fragment_join=""
	fi
done < traffic_reversed
rm -rf traffic_reversed

#reverse again
tac traffic_reversed_decoded > traffic_decoded
rm -rf traffic_reversed_decoded

#show lines containing data
cat traffic_decoded
rm -rf traffic_decoded





