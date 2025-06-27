#!/bin/bash

table=$1
filename=$2

bq load \
--source_format=NEWLINE_DELIMITED_JSON \
--autodetect \
${table} \
${filename}
