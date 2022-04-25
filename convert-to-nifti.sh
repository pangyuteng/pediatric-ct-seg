#!/bin/bash

inputdir=$1
outputdir=$2

docker run -it \
	-u $(id -u):$(id -g) \
	-e inputdir=$inputdir \
	-e outputdir=$outputdir \
	-v $inputdir:$inputdir \
	-v $outputdir:$outputdir \
	-w /workdir -v $PWD:/workdir \
	pediatric-ct-seg bash 
	

