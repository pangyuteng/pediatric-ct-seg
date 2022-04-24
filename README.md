# pediatric-ct-seg

+ download tcia file.

```
bash download-tcia-file.sh
```

+ use tcia rest api to download files and unzip

```
for example with code here: https://github.com/pangyuteng/tcia-image-download-python

export outputdir=/mnt/hd2/data/ped-ct-seg
python download.py Pediatric-CT-SEG-Mar-22-2022-manifest.tcia $outputdir

```

+ convert dicom and rtstruct to nifti
```
docker build -t pediatric-ct-seg .
bash convert-to-nifti.sh $inputdir $outputdir
bash convert-to-nifti.sh /mnt/hd2/data/ped-ct-seg /mnt/hd/data/ped-ct-seg-nifti
```









```
