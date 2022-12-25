import os
import sys
import json
import numpy as np
import SimpleITK as sitk
from dcmrtstruct2nii import dcmrtstruct2nii, list_rt_structs

rt_file=sys.argv[1]
dcm_folder=sys.argv[2]
mask_folder=sys.argv[3]
output_nifti_file =sys.argv[4]

dcmrtstruct2nii(rt_file,dcm_folder,mask_folder)

def imread(fpath):
    reader= sitk.ImageFileReader()
    reader.SetFileName(fpath)
    return reader.Execute()

with open('organ_mapper.json','r') as f:
    mapper = json.loads(f.read())
mapper = {k.replace(' ','-'):v for k,v in mapper.items()}

img_file = os.path.join(mask_folder,'image.nii.gz')
print('reading',img_file)
img_obj = imread(img_file)
print('done')
img = sitk.GetArrayFromImage(img_obj)
mainmask = np.zeros_like(img)
file_path_list = [os.path.join(mask_folder,x) for x in os.listdir(mask_folder)]
for file_path in file_path_list:
    basename = os.path.basename(file_path)
    organ = basename.replace("mask_",'').replace(".nii.gz",'')
    if organ == 'Skin':
        continue
    if organ in list(mapper.keys()):
        print(organ,file_path)
        int_value = mapper[organ]
        if int_value == 0:
            continue
        mask_obj = imread(file_path)
        mask = sitk.GetArrayFromImage(mask_obj)
        print(np.sum(mask),np.unique(mask))
        mainmask[mask>0] = int_value

mainmask = mainmask.astype(np.int16)
mainmask = mainmask[::-1,:,:] #? unsure if this is ok?
print(np.unique(mainmask))
mask_obj = sitk.GetImageFromArray(mainmask)
mask_obj.CopyInformation(img_obj)
writer = sitk.ImageFileWriter()
writer.SetFileName(output_nifti_file)
writer.SetUseCompression(True)
writer.Execute(mask_obj)