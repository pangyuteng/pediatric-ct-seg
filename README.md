

# pediatric-ct-seg

### summary

```
repo contains scripts used to download and view the `Pediatric-CT-SEG` dataset

```

### `Pediatric-CT-SEG` dataset

```

Jordan, P., Adamson, P. M., Bhattbhatt, V., Beriwal, S., Shen, S., Radermecker, O., Bose, S., Strain, L. S., Offe, M., Fraley, D., Principi, S., Ye, D. H., Wang, A. S., Van Heteren, J., Vo, N.-J., & Schmidt, T. G. (2021). Pediatric Chest/Abdomen/Pelvic CT Exams with Expert Organ Contours (Pediatric-CT-SEG) (Version 2) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.X0H0-1706

https://wiki.cancerimagingarchive.net/pages/viewpage.action?pageId=89096588

```


### steps

+ download tcia file.

```
bash download-tcia-file.sh
```

+ use tcia rest api to download files and unzip

```
for example with code here: https://github.com/pangyuteng/tcia-image-download-python

export inputdir=/mnt/hd2/data/ped-ct-seg
python download.py Pediatric-CT-SEG-Mar-22-2022-manifest.tcia $inputdir

```

+ convert dicom and rtstruct to nifti

```

docker build -t pediatric-ct-seg .
export inputdir=/mnt/hd2/data/ped-ct-seg
export outputdir=/mnt/hd/data/ped-ct-seg-nifti
mkdir -p $outputdir

bash convert-to-nifti.sh $inputdir $outputdir
python dcm2nifti.py $inputdir $outputdir

```









```
