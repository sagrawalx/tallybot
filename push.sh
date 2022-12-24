#!/bin/bash

if [[ -z "$1" ]]; then
  echo "Please enter a git commit message"
  exit
fi

git add . && git commit -m "$1"
git push origin main
