import os
import sys
import ast
import json
import time
import argparse
import traceback
import hashlib
import numpy as np
import pandas as pd
import pydicom
from tqdm import tqdm
from rt_utils import RTStructBuilder
import SimpleITK as sitk


skip = [
    "De-identification Method",
    "De-identification Method Code Sequence",
    "Private Creator",
    "Private tag data",
    "Private tag data",
    "Longitudinal Temporal Information Modified",
    "Structure Set Label",
    "Structure Set Name",
    "Structure Set Date",
    "Structure Set Time",
    "Referenced Frame of Reference Sequence",
    "Structure Set ROI Sequence",
    "ROI Contour Sequence",
    "RT ROI Observations Sequence",
    "Approval Status",
    "Specific Character Set",    
    "Coding Scheme Identification Sequence",
    "Context Group Identification Sequence",
    "Mapping Resource Identification Sequence",
    "Patient Identity Removed",
]

uncleaned_organ_json = 'uncleaned_organ.json'
with open(uncleaned_organ_json,'r') as f:
    UNCLEANED_ORGAN_ENUM_DICT = json.loads(f.read())

with open("organ_mapper.json",'r') as f:
    ORGAN_MAPPER = json.loads(f.read())
dcmdump_csv = 'retry-cases.csv'

DICOM_ROOT = '/mnt/hd2/data/ped-ct-seg'

def myjob(outputdir,PatientName,patch_rt):
    df = pd.read_csv(dcmdump_csv)
    
    subject_folder_path = os.path.join(outputdir,PatientName)
    os.makedirs(subject_folder_path,exist_ok=True)
    image_file = os.path.join(subject_folder_path,'image.nii.gz')
    mask_preprocessed_file = os.path.join(subject_folder_path,'mask_preprocessed.nii.gz')
    print(os.path.exists(image_file),image_file)
    print(os.path.exists(mask_preprocessed_file),mask_preprocessed_file)
    print('will attempt to generate above...')

    rt = df[(df["PatientID"]==PatientName)&(df.Modality=="RTSTRUCT")].reset_index()
    ds = df[(df["PatientID"]==PatientName)&(df.Modality=="CT")].reset_index()
    if len(rt)!=1 or len(ds)!=1:
        print(f'missing? {PatientName} rt {len(rt)} ds {len(ds)}')
        return #continue

    ds_folder_path = os.path.join(DICOM_ROOT,ds.SeriesInstanceUID[0])
    rt_folder = os.path.join(DICOM_ROOT,rt.SeriesInstanceUID[0])
    rt_file = os.path.join(rt_folder,os.listdir(rt_folder)[0])
    
    print('ds_folder_path',ds_folder_path)
    print('rt_file',rt_file)
    rt = pydicom.dcmread(rt_file)
    ReferencedSOPInstanceUID_list = [x[(0x0008,0x1155)].value for x in rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]]
    
    SOPInstanceUID_list = []
    for basename in os.listdir(ds_folder_path):
        ds_file = os.path.join(ds_folder_path,basename)
        SOPInstanceUID = pydicom.dcmread(ds_file)['SOPInstanceUID'].value
        SOPInstanceUID_list.append(SOPInstanceUID)

    no_match_list = []
    for ReferencedSOPInstanceUID in ReferencedSOPInstanceUID_list:
        if ReferencedSOPInstanceUID not in SOPInstanceUID_list:
            no_match_list.append(ReferencedSOPInstanceUID)

    if patch_rt:
        print('in 3 seconds we will patch RT_STRUCT!')
        time.sleep(5)
        rt = pydicom.dcmread(rt_file)
        tmp = rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]
        new_list = []
        for x in tmp:
            if x[(0x0008,0x1155)].value in SOPInstanceUID_list:
                new_list.append(x)                    
        rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)].value=new_list
        rt_file = '/tmp/newfile.dcm'
        pydicom.dcmwrite(rt_file, rt,write_like_original=True)
        rt = pydicom.dcmread(rt_file)
        ReferencedSOPInstanceUID_list = [x[(0x0008,0x1155)].value for x in rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]]
        no_match_list = []
        for ReferencedSOPInstanceUID in ReferencedSOPInstanceUID_list:
            if ReferencedSOPInstanceUID not in SOPInstanceUID_list:
                no_match_list.append(ReferencedSOPInstanceUID)

    if len(no_match_list)>0:
        print(len(no_match_list),len(ReferencedSOPInstanceUID_list),len(SOPInstanceUID_list))
        raise ValueError('no matching SOPInstanceUID_list')

    if not os.path.exists(image_file):

        dcm_list = []
        for x in os.listdir(ds_folder_path):
            dcm_file = os.path.join(ds_folder_path,x)
            ds = pydicom.dcmread(dcm_file,stop_before_pixels=True)
            dcm_list.append([ds.InstanceNumber,dcm_file])

        dcm_list = sorted(dcm_list,key=lambda x: x[0])
        dicom_names = [x[1] for x in dcm_list]
        dicom_names = dicom_names

        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(dicom_names)
        img_obj = reader.Execute()
        image = sitk.GetArrayFromImage(img_obj)
        spacing = img_obj.GetSpacing()
        origin = img_obj.GetOrigin()
        direction = img_obj.GetDirection() 
    
        writer = sitk.ImageFileWriter()
        writer.SetFileName(image_file)
        writer.SetUseCompression(True)
        writer.Execute(img_obj)

    if not os.path.exists(mask_preprocessed_file):
        print('ds_folder_path',ds_folder_path)
        print('rt_file',rt_file)
        try:
            rtstruct = RTStructBuilder.create_from(
                dicom_series_path=ds_folder_path, 
                rt_struct_path=rt_file,
            )
        except:
            traceback.print_exc()
            return #continue
                    
        reader= sitk.ImageFileReader()
        reader.SetFileName(image_file)
        img_obj = reader.Execute()
        image = sitk.GetArrayFromImage(img_obj)
        mask = np.zeros_like(image)

        print(f'image shape {image.shape}')
        for roi_name in rtstruct.get_roi_names():
            try:
                mask_3d = rtstruct.get_roi_mask_by_name(roi_name)
                print(f"mask_3d {mask_3d.shape}")
                mask_3d = np.swapaxes(mask_3d, 1, 2)
                mask_3d = np.swapaxes(mask_3d, 0, 1)
                target_value = ORGAN_MAPPER[roi_name]
                mask[mask_3d>0] = target_value

            except:
                traceback.print_exc()
                print(roi_name,'!!!')
                
        print(mask.shape,np.unique(mask))
        mask = mask.astype(np.uint8)
        mask = mask[::-1,:,:] #? unsure if this is ok?
        mask_obj = sitk.GetImageFromArray(mask)
        mask_obj.SetSpacing(img_obj.GetSpacing())
        mask_obj.SetOrigin(img_obj.GetOrigin())
        mask_obj.SetDirection(img_obj.GetDirection() )
        writer = sitk.ImageFileWriter()    
        writer.SetFileName(mask_preprocessed_file)
        writer.SetUseCompression(True)
        writer.Execute(mask_obj)

    return True
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('outputdir')
    parser.add_argument('PatientName')
    parser.add_argument('-p', '--patch_rt',action='store_true')
    args = parser.parse_args()
    myjob(args.outputdir,args.PatientName,args.patch_rt)

"""
use below to locate 4 cases that dcm2nifti.py errored out on.
>>> df=pd.read_csv('image-mask-list.csv')
>>> a=os.listdir('/mnt/hd2/data/ped-ct-seg-nifti')
>>> set(a)-set(df.PatientName)
{'Pediatric-CT-SEG-272B6C5D', 'Pediatric-CT-SEG-CAB73EEC', 'Pediatric-CT-SEG-34ECBB32', 'Pediatric-CT-SEG-14403912'}


python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-14403912

python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-272B6C5D
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-CAB73EEC
above viewed with ITKSNAP, contours are missing slices!

below case showed no mask...
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-34ECBB32
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-C7338499

pip install dcmrtstruct2nii
export rt_file=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.1.25927210562287345060498125954444953116/1-fa0d96fce842f0a48096d8d1a2977b27.dcm
export dcm_folder=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.160098151550784443282129329572672487102
export nifti_folder=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-34ECBB32/masks
export nifti_file=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-34ECBB32/mask_preprocessed.nii.gz
python fix-last-case.py $rt_file $dcm_folder $nifti_folder $nifti_file

# delete the $nifti_folder

export rt_file
export dcm_folder
export nifti_folder
export nifti_file

export rt_file=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.1.17305113025728199346750740188024809813/1-cd3fd493dcf44c9353c3e19fa962e5e4.dcm
export dcm_folder=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.336975195064431029632182792210605161857
export nifti_folder=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-272B6C5D/masks
export nifti_file=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-272B6C5D/mask_preprocessed.nii.gz
python fix-last-case.py $rt_file $dcm_folder $nifti_folder $nifti_file

export rt_file=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.175594891989977819790310921126823896785/1-c35345fb73bfa2a5556f0f6332f00709.dcm
export dcm_folder=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.161494771169616128771736064327557201788
export nifti_folder=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-CAB73EEC/masks
export nifti_file=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-CAB73EEC/mask_preprocessed.nii.gz
python fix-last-case.py $rt_file $dcm_folder $nifti_folder $nifti_file


Pediatric-CT-SEG-C7338499

1.3.6.1.4.1.14519.5.2.1.260321938736326085125972766634789836424,1.3.6.1.4.1.14519.5.2.1.294789660809722318580941683858436001056,CT,2009-10-12,CT,30144.000000,Pediatric-CT-SEG,GE MEDICAL SYSTEMS,Revolution CT,revo_ct_21a.33,1,152,ABDOMEN,Pediatric-CT-SEG-C7338499,Pediatric-CT-SEG-C7338499,F,2009-10-12,CT,003Y,2
1.3.6.1.4.1.14519.5.2.1.1.24786082590222911565820263531922721785,1.3.6.1.4.1.14519.5.2.1.294789660809722318580941683858436001056,RTSTRUCT,,,2.000000,Pediatric-CT-SEG,Varian Medical Systems,ARIA RTM,4.2.7.0,1,1,,Pediatric-CT-SEG-C7338499,Pediatric-CT-SEG-C7338499,F,2009-10-12,CT,003Y,2

export rt_file=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.1.24786082590222911565820263531922721785/1-f9bfd4e3fcb53b6843052f22ea818c49.dcm
export dcm_folder=/mnt/hd2/data/ped-ct-seg/1.3.6.1.4.1.14519.5.2.1.260321938736326085125972766634789836424
export nifti_folder=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-C7338499/masks
export nifti_file=/mnt/hd2/data/ped-ct-seg-nifti/Pediatric-CT-SEG-C7338499/mask_preprocessed.nii.gz


"""