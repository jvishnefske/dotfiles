#!/bin/sh
if ping -c 1 10.1.0.1 
then mount /mnt/nfs
fi
